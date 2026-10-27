"""DB-free contracts for scoped, accent-insensitive keyset feed queries."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from app.api.dependencies import get_current_user
from app.api.v1.classroom_posts import router
from app.core.database import get_session
from app.core.exceptions import AppError
from app.repositories.classroom_feed_search import normalize_feed_search
from app.repositories.classroom_posts import ClassroomPostRepository
from app.services.classroom_posts import (
    ClassroomPostService,
    _decode_cursor,
    _encode_cursor,
    _FeedCursor,
)
from tests.test_classroom_classwork_unit import actor, classroom, session_double


@pytest.mark.parametrize(
    "value,expected",
    [
        ("  ĐỀ   ôn tập ", "de on tap"),
        ("Đề ôn", "de on"),
        ("WRITING", "writing"),
        ("%_ /", "%_ /"),
        (None, ""),
    ],
)
def test_normalization_matches_vietnamese_precomposed_and_combining_text(value, expected):
    assert normalize_feed_search(value) == expected


def test_direct_service_search_length_is_bounded():
    with pytest.raises(AppError) as caught:
        normalize_feed_search("x" * 201)
    assert caught.value.code == "INVALID_FEED_SEARCH"


@pytest.mark.parametrize("staff,pinned", [(False, False), (True, False), (False, True)])
async def test_repository_keeps_search_pin_visibility_and_cursor_in_one_bounded_query(
    staff, pinned
):
    session = session_double()
    result = Mock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    room_id = uuid4()
    await ClassroomPostRepository(session).feed_keys(
        room_id,
        staff=staff,
        status=None,
        cursor=(True, datetime.now(UTC), "ANNOUNCEMENT", uuid4()),
        limit=20,
        search="de %_",
        pinned_only=pinned,
    )
    statement = session.execute.call_args.args[0]
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert session.execute.await_count == 1
    assert sql.count(str(room_id)) >= 3
    assert "UNION ALL" in sql and "LIMIT 21" in sql and "ORDER BY classroom_feed.pinned DESC" in sql
    assert "translate(lower(concat_ws" in sql and "ESCAPE '/'" in sql
    assert "/%/_" in statement.compile(dialect=postgresql.dialect()).params.values()
    assert "classroom_posts.deleted_at IS NULL" in sql
    assert "classroom_resources.status = 'PUBLISHED'" in sql
    assert "NOT (EXISTS" in sql  # Retains canonical attachment de-duplication.
    if not staff:
        assert "classroom_posts.status = 'PUBLISHED'" in sql
        assert "classroom_sections.status = 'PUBLISHED'" in sql
    if pinned:
        assert "classroom_posts.pinned IS true" in sql
        assert "classroom_posts.kind = 'ANNOUNCEMENT'" in sql
    assert "storage_key" not in sql and "answer_key" not in sql


def feed_service():
    owner = actor()
    room = classroom(owner)
    service = ClassroomPostService(session_double(), owner)
    service.access.room = AsyncMock(return_value=room)
    service.access.staff = Mock(return_value=False)
    for method in (
        "feed_keys",
        "posts_with_authors",
        "assignments_with_authors",
        "resources_with_authors",
    ):
        setattr(service.repository, method, AsyncMock(return_value=[]))
    service.repository.comment_counts = AsyncMock(return_value={})
    service.repository.resource_ids = AsyncMock(return_value={})
    return service, room


@pytest.mark.parametrize(
    "changed",
    [
        {"search": "other"},
        {"pinned_only": False},
        {"content_kind": "DISCUSSION"},
        {"classroom_id": uuid4()},
        {"status": "DRAFT"},
    ],
)
async def test_cursor_rejects_changes_to_search_pin_kind_room_or_status(changed):
    service, room = feed_service()
    service.access.staff.return_value = True
    cursor = _FeedCursor(
        classroom_id=room.id,
        status=None,
        search="de on",
        pinned_only=True,
        pinned=True,
        created_at=datetime.now(UTC),
        kind="ANNOUNCEMENT",
        id=uuid4(),
    )
    options = {"classroom_id": room.id, "search": "ĐỀ ÔN", "pinned_only": True, **changed}
    with pytest.raises(AppError) as caught:
        await service.feed(**options, cursor=_encode_cursor(cursor))
    assert caught.value.code == "INVALID_CURSOR"
    service.repository.feed_keys.assert_not_awaited()


async def test_equivalent_accented_search_retains_its_cursor_scope():
    service, room = feed_service()
    cursor = _FeedCursor(
        classroom_id=room.id,
        status=None,
        search="de on",
        pinned_only=True,
        pinned=True,
        created_at=datetime.now(UTC),
        kind="ANNOUNCEMENT",
        id=uuid4(),
    )
    assert (
        await service.feed(
            room.id, search=" ĐỀ  ÔN ", pinned_only=True, cursor=_encode_cursor(cursor)
        )
    ).items == []
    assert service.repository.feed_keys.call_args.kwargs["search"] == "de on"
    assert service.repository.feed_keys.call_args.kwargs["pinned_only"] is True


async def test_next_cursor_contains_normalized_search_and_pin_scope():
    service, room = feed_service()
    stamp = datetime.now(UTC)
    keys = [
        SimpleNamespace(id=uuid4(), kind="ANNOUNCEMENT", created_at=stamp, pinned=True)
        for _ in range(2)
    ]
    service.repository.feed_keys.return_value = keys
    page = await service.feed(room.id, search="ĐỀ ôn", pinned_only=True, limit=1)
    decoded = _decode_cursor(page.next_cursor, _FeedCursor)
    assert decoded.search == "de on" and decoded.pinned_only is True
    assert decoded.id == keys[0].id and decoded.created_at == stamp
    # Hydration can lose a row to a concurrent archive/delete without losing the keyset.
    assert page.items == [] and page.next_cursor


async def test_search_does_not_grant_student_draft_or_unreadable_classroom_access():
    service, room = feed_service()
    with pytest.raises(AppError) as caught:
        await service.feed(room.id, search="secret", status="DRAFT")
    assert caught.value.status_code == 403
    service.repository.feed_keys.assert_not_awaited()
    service.access.room.side_effect = AppError("CLASSROOM_NOT_ACCESSIBLE", "Denied", 404)
    with pytest.raises(AppError):
        await service.feed(room.id, search="secret", pinned_only=True)
    service.repository.feed_keys.assert_not_awaited()


async def test_http_search_bounds_and_optional_pin_filter_are_validated_without_database(
    monkeypatch,
):
    user = actor()
    feed = AsyncMock(return_value={"items": [], "next_cursor": None})
    monkeypatch.setattr(ClassroomPostService, "feed", feed)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: session_double()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/classrooms/{uuid4()}/feed"
        assert (await client.get(path, params={"search": "x" * 201})).status_code == 422
        assert (await client.get(path, params={"pinned_only": "invalid"})).status_code == 422
        feed.assert_not_awaited()
        assert (
            await client.get(path, params={"search": "Đề ôn", "pinned_only": "true"})
        ).status_code == 200
        assert feed.call_args.kwargs["search"] == "Đề ôn"
        assert feed.call_args.kwargs["pinned_only"] is True

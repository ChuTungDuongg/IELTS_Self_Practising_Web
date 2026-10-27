"""Run only with an isolated PostgreSQL test database; all content is fictional."""

import pytest

from app.schemas.classroom_posts import PostCreate, PostUpdate
from tests.test_classroom_posts import assert_error, fixture, service

pytestmark = pytest.mark.integration


async def test_vietnamese_search_pages_are_complete_pinned_and_visibility_scoped(db_session):
    teacher, student, outsider, room = await fixture(db_session)
    saved = []
    for number in range(5):
        saved.append(
            await service(db_session, teacher).create(
                room,
                PostCreate(
                    kind="ANNOUNCEMENT",
                    title=f"Đề ôn tập {number}",
                    body="Fictional lesson",
                    status="PUBLISHED",
                ),
            )
        )
    await service(db_session, teacher).create(
        room,
        PostCreate(
            kind="ANNOUNCEMENT", title="Đề ôn bí mật", body="Fictional draft", status="DRAFT"
        ),
    )
    for post in saved[:2]:
        await service(db_session, teacher).update(room, post.id, PostUpdate(pinned=True))
    seen, cursor = [], None
    while True:
        page = await service(db_session, student).feed(room, search="DE ON", limit=2, cursor=cursor)
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 5
    assert set(seen) == {post.id for post in saved}
    page = await service(db_session, student).feed(room, search="de on", pinned_only=True, limit=1)
    assert page.items[0].pinned and page.next_cursor
    await assert_error(
        lambda: service(db_session, student).feed(
            room, search="other", pinned_only=True, cursor=page.next_cursor
        ),
        "INVALID_CURSOR",
    )
    await assert_error(
        lambda: service(db_session, outsider).feed(room, search="de on"), "CLASSROOM_NOT_FOUND"
    )

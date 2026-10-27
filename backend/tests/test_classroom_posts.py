"""Fictional Feed fixtures exercise the real classroom authorization and transactions."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app.core.exceptions import AppError
from app.main import app
from app.models import Classroom, ClassroomAssignment, ClassroomMembership, Notification
from app.models.enums import AssignmentStatus, NotificationType, UserRole, VersionStatus
from tests.teacher_helpers import api_client, make_user, make_version


def test_feed_api_exposes_explicit_post_and_comment_routes():
    routes = app.openapi()["paths"]
    for path, methods in {
        "/api/v1/classrooms/{classroom_id}/feed": {"get"},
        "/api/v1/classrooms/{classroom_id}/posts": {"post"},
        "/api/v1/classrooms/{classroom_id}/posts/{post_id}": {"get", "patch"},
        "/api/v1/classrooms/{classroom_id}/posts/{post_id}/comments": {"get", "post"},
        "/api/v1/classrooms/{classroom_id}/comments/{comment_id}": {"patch", "delete"},
    }.items():
        assert path in routes
        assert methods <= routes[path].keys()


def test_post_and_comment_schemas_reject_blank_overlong_and_privileged_payloads():
    from pydantic import ValidationError

    from app.schemas.classroom_posts import CommentCreate, PostCreate, PostUpdate

    for payload in (
        {"kind": "ANNOUNCEMENT", "body": " "},
        {"kind": "ANNOUNCEMENT", "body": "x" * 20001},
        {"kind": "ASSIGNMENT_ACTIVITY", "body": "Independent assignment"},
        {"kind": "DISCUSSION", "body": "Notes", "author_id": str(uuid4())},
    ):
        with pytest.raises(ValidationError):
            PostCreate(**payload)
    reference = uuid4()
    with pytest.raises(ValidationError):
        PostCreate(kind="DISCUSSION", body="Notes", resource_ids=[reference, reference])
    for payload in ({}, {"body": None}, {"resource_ids": None}, {"locked": None}):
        with pytest.raises(ValidationError):
            PostUpdate(**payload)
    assert PostUpdate(title=None).model_fields_set == {"title"}
    for body in (" ", "x" * 5001):
        with pytest.raises(ValidationError):
            CommentCreate(body=body)
    assert PostCreate(kind="DISCUSSION", body=" **Fictional notes** ").body == "**Fictional notes**"


def test_feed_cursors_preserve_pin_timestamp_kind_uuid_and_reject_invalid_data():
    import base64
    import json

    from app.services.classroom_posts import (
        _CommentCursor,
        _decode_cursor,
        _encode_cursor,
        _FeedCursor,
    )

    cursor = _FeedCursor(
        classroom_id=uuid4(),
        status=None,
        pinned=True,
        created_at=datetime(2026, 10, 27, tzinfo=UTC),
        kind="DISCUSSION",
        id=uuid4(),
    )
    encoded = _encode_cursor(cursor)
    assert _decode_cursor(encoded, _FeedCursor) == cursor
    payload = cursor.model_dump(mode="json")
    for changed in (
        {"pinned": "false"},
        {"version": 2},
        {"created_at": "2026-10-27T00:00:00"},
        {"kind": "UNKNOWN"},
    ):
        malformed = base64.urlsafe_b64encode(json.dumps({**payload, **changed}).encode()).decode()
        with pytest.raises(AppError) as error:
            _decode_cursor(malformed, _FeedCursor)
        assert error.value.code == "INVALID_CURSOR"
    for malformed in ("bad!", "x" * 2049, "", "e30"):
        with pytest.raises(AppError):
            _decode_cursor(malformed, _FeedCursor)
    comment = _CommentCursor(post_id=uuid4(), created_at=cursor.created_at, id=uuid4())
    assert _decode_cursor(_encode_cursor(comment), _CommentCursor) == comment
    with pytest.raises(AppError):
        _decode_cursor(encoded, _CommentCursor)


def test_comment_tombstones_redact_body_and_preserve_audit_content():
    from app.models.classroom_posts import ClassroomComment
    from app.services.classroom_posts import ClassroomPostService

    author_id = uuid4()
    from app.models import User

    author = User(id=author_id, display_name="Fictional learner")
    comment = ClassroomComment(
        id=uuid4(),
        post_id=uuid4(),
        author_id=author_id,
        body="Audit text",
        state="MODERATED",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    response = ClassroomPostService._comment_response(comment, author)
    assert response.body == "" and response.state == "MODERATED"
    assert comment.body == "Audit text"
    comment.state = "RETRACTED"
    assert ClassroomPostService._comment_response(comment, author).body == ""
    comment.state = "VISIBLE"
    assert ClassroomPostService._comment_response(comment, author).body == "Audit text"


async def fixture(session):
    teacher = await make_user(session, UserRole.TEACHER)
    student = await make_user(session)
    other = await make_user(session)
    async with session.begin():
        room = Classroom(teacher_id=teacher.id, name="Fictional discussion workshop")
        session.add(room)
        await session.flush()
        session.add(ClassroomMembership(classroom_id=room.id, user_id=student.id))
        await session.flush()
    return teacher, student, other, room.id


def service(session, actor):
    from app.services.classroom_posts import ClassroomPostService

    return ClassroomPostService(session, actor)


async def post(session, actor, room_id, **overrides):
    from app.schemas.classroom_posts import PostCreate

    return await service(session, actor).create(
        room_id,
        PostCreate(kind="ANNOUNCEMENT", body="**Fictional** workshop notes", **overrides),
    )


async def assert_error(operation, code):
    with pytest.raises(AppError) as caught:
        await operation()
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_drafts_publication_notification_idempotency_and_archival(db_session):
    from app.schemas.classroom_posts import PostUpdate

    teacher, student, outsider, room_id = await fixture(db_session)
    draft = await post(db_session, teacher, room_id)
    assert draft.status == "DRAFT" and draft.published_at is None
    assert (await service(db_session, student).feed(room_id)).items == []
    await assert_error(
        lambda: service(db_session, student).get(room_id, draft.id), "CLASSROOM_POST_NOT_FOUND"
    )
    await assert_error(
        lambda: service(db_session, outsider).get(room_id, draft.id), "CLASSROOM_NOT_FOUND"
    )
    assert (await service(db_session, teacher).feed(room_id)).items[0].id == draft.id
    published = await service(db_session, teacher).publish(room_id, draft.id)
    assert published.published_at is not None
    await service(db_session, teacher).publish(room_id, draft.id)
    await service(db_session, teacher).update(room_id, draft.id, PostUpdate(body="Edited notes"))
    async with db_session.begin():
        notices = list(
            await db_session.scalars(
                select(Notification).where(
                    Notification.type == NotificationType.CLASSROOM_ANNOUNCEMENT_PUBLISHED,
                    Notification.entity_id == draft.id,
                )
            )
        )
    assert len(notices) == 1 and notices[0].user_id == student.id
    assert notices[0].payload_json["classroom_id"] == str(room_id)
    await service(db_session, teacher).archive(room_id, draft.id)
    assert (await service(db_session, student).feed(room_id)).items == []
    await assert_error(
        lambda: service(db_session, student).get(room_id, draft.id), "CLASSROOM_POST_NOT_FOUND"
    )
    assert (await service(db_session, teacher).feed(room_id, status="ARCHIVED")).items[
        0
    ].id == draft.id
    await service(db_session, teacher).publish(room_id, draft.id)
    async with db_session.begin():
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.entity_id == draft.id)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_announcement_notifies_only_active_enrolled_accounts_at_first_publication(db_session):
    from app.models import User
    from app.schemas.classroom_posts import PostCreate

    teacher, student, former, room_id = await fixture(db_session)
    inactive = await make_user(db_session)
    enrolled_teacher = await make_user(db_session, UserRole.TEACHER)
    async with db_session.begin():
        db_session.add_all(
            [
                ClassroomMembership(
                    classroom_id=room_id, user_id=former.id, left_at=datetime.now(UTC)
                ),
                ClassroomMembership(classroom_id=room_id, user_id=inactive.id),
                ClassroomMembership(classroom_id=room_id, user_id=enrolled_teacher.id),
            ]
        )
        (await db_session.get(User, inactive.id)).is_active = False
    discussion = await service(db_session, teacher).create(
        room_id, PostCreate(kind="DISCUSSION", body="Fictional discussion", status="PUBLISHED")
    )
    announcement = await post(db_session, teacher, room_id, status="PUBLISHED")
    async with db_session.begin():
        recipients = list(
            await db_session.scalars(
                select(Notification.user_id).where(Notification.entity_id == announcement.id)
            )
        )
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.entity_id == discussion.id)
            )
            == 0
        )
    assert set(recipients) == {student.id, enrolled_teacher.id}


@pytest.mark.asyncio
async def test_admin_comments_stay_read_only_with_membership_and_legacy_comment_ownership(
    db_session,
):
    from app.models.classroom_posts import ClassroomComment
    from app.schemas.classroom_posts import CommentCreate, CommentUpdate

    teacher, student, _, room_id = await fixture(db_session)
    admin = db_session.info["current_user_identity"]
    published = await post(db_session, teacher, room_id, status="PUBLISHED")
    student_comment = await service(db_session, student).create_comment(
        room_id, published.id, CommentCreate(body="Student question")
    )
    await assert_error(
        lambda: service(db_session, admin).create_comment(
            room_id, published.id, CommentCreate(body="Unenrolled admin")
        ),
        "CLASSROOM_OBSERVER_READ_ONLY",
    )
    async with db_session.begin():
        db_session.add(ClassroomMembership(classroom_id=room_id, user_id=admin.id))
        own = ClassroomComment(
            post_id=published.id, author_id=admin.id, body="Legacy administrator comment"
        )
        db_session.add(own)
        await db_session.flush()
        own_id = own.id
    assert {
        comment.id
        for comment in (await service(db_session, admin).comments(room_id, published.id)).items
    } == {student_comment.id, own_id}
    await assert_error(
        lambda: service(db_session, admin).create_comment(
            room_id, published.id, CommentCreate(body="Enrolled admin")
        ),
        "CLASSROOM_OBSERVER_READ_ONLY",
    )
    await assert_error(
        lambda: service(db_session, admin).update_comment(
            room_id, own_id, CommentUpdate(body="Edited own comment")
        ),
        "CLASSROOM_OBSERVER_READ_ONLY",
    )
    await assert_error(
        lambda: service(db_session, admin).delete_comment(room_id, own_id),
        "CLASSROOM_OBSERVER_READ_ONLY",
    )
    await assert_error(
        lambda: service(db_session, admin).delete_comment(room_id, student_comment.id),
        "CLASSROOM_OBSERVER_READ_ONLY",
    )
    comments = (await service(db_session, admin).comments(room_id, published.id)).items
    assert {comment.id: comment.body for comment in comments} == {
        student_comment.id: "Student question",
        own_id: "Legacy administrator comment",
    }


@pytest.mark.asyncio
async def test_owner_only_post_mutations_admin_oversight_and_room_isolation(db_session):
    teacher, student, outsider, room_id = await fixture(db_session)
    another_teacher = await make_user(db_session, UserRole.TEACHER)
    admin = db_session.info["current_user_identity"]
    draft = await post(db_session, teacher, room_id)
    assert (await service(db_session, admin).get(room_id, draft.id)).id == draft.id
    for actor in (student, admin):
        await assert_error(
            lambda actor=actor: service(db_session, actor).publish(room_id, draft.id),
            "CLASSROOM_OBSERVER_READ_ONLY"
            if actor.role == UserRole.ADMIN
            else "CLASSROOM_OWNERSHIP_REQUIRED",
        )
    await assert_error(
        lambda: service(db_session, another_teacher).publish(room_id, draft.id),
        "CLASSROOM_NOT_FOUND",
    )
    other_room = await fixture(db_session)
    await assert_error(
        lambda: service(db_session, other_room[0]).get(other_room[3], draft.id),
        "CLASSROOM_POST_NOT_FOUND",
    )
    await assert_error(
        lambda: service(db_session, student).feed(room_id, status="DRAFT"),
        "CLASSROOM_OWNERSHIP_REQUIRED",
    )


@pytest.mark.asyncio
async def test_comments_ownership_retraction_moderation_locks_and_former_members(db_session):
    from app.schemas.classroom_posts import CommentCreate, CommentUpdate, PostUpdate
    from app.services.classrooms import ClassroomService

    teacher, student, outsider, room_id = await fixture(db_session)
    published = await post(db_session, teacher, room_id, status="PUBLISHED")
    student_service = service(db_session, student)
    comment = await student_service.create_comment(
        room_id, published.id, CommentCreate(body="A question")
    )
    edited = await student_service.update_comment(
        room_id, comment.id, CommentUpdate(body="A clearer question")
    )
    assert edited.body == "A clearer question"
    await assert_error(
        lambda: service(db_session, teacher).update_comment(
            room_id, comment.id, CommentUpdate(body="Rewritten")
        ),
        "COMMENT_OWNERSHIP_REQUIRED",
    )
    await assert_error(
        lambda: service(db_session, outsider).create_comment(
            room_id, published.id, CommentCreate(body="Intrusion")
        ),
        "CLASSROOM_NOT_FOUND",
    )
    moderated = await service(db_session, teacher).delete_comment(room_id, comment.id)
    assert moderated.state == "MODERATED" and moderated.body == ""
    await assert_error(
        lambda: student_service.update_comment(room_id, comment.id, CommentUpdate(body="Restored")),
        "CLASSROOM_COMMENT_REMOVED",
    )
    own = await student_service.create_comment(
        room_id, published.id, CommentCreate(body="Another question")
    )
    retracted = await student_service.delete_comment(room_id, own.id)
    assert retracted.state == "RETRACTED" and retracted.body == ""
    await service(db_session, teacher).update(room_id, published.id, PostUpdate(locked=True))
    await assert_error(
        lambda: student_service.create_comment(room_id, published.id, CommentCreate(body="Locked")),
        "CLASSROOM_POST_LOCKED",
    )
    await service(db_session, teacher).update(room_id, published.id, PostUpdate(locked=False))
    await ClassroomService(db_session, student).leave(room_id)
    assert len((await student_service.comments(room_id, published.id)).items) == 2
    await assert_error(
        lambda: student_service.create_comment(
            room_id, published.id, CommentCreate(body="Former member")
        ),
        "ACTIVE_MEMBERSHIP_REQUIRED",
    )


@pytest.mark.asyncio
async def test_archived_classroom_preserves_reads_and_rejects_all_new_feed_mutations(db_session):
    from app.schemas.classroom_posts import CommentCreate, CommentUpdate, PostUpdate
    from app.services.classrooms import ClassroomService

    teacher, student, _, room_id = await fixture(db_session)
    published = await post(db_session, teacher, room_id, status="PUBLISHED")
    comment = await service(db_session, student).create_comment(
        room_id, published.id, CommentCreate(body="Retained")
    )
    await ClassroomService(db_session, teacher).archive(room_id)
    assert (await service(db_session, student).get(room_id, published.id)).body == published.body
    for operation in (
        lambda: post(db_session, teacher, room_id),
        lambda: service(db_session, teacher).publish(room_id, published.id),
        lambda: service(db_session, teacher).archive(room_id, published.id),
        lambda: service(db_session, teacher).update(room_id, published.id, PostUpdate(pinned=True)),
        lambda: service(db_session, student).create_comment(
            room_id, published.id, CommentCreate(body="Too late")
        ),
        lambda: service(db_session, student).update_comment(
            room_id, comment.id, CommentUpdate(body="Too late")
        ),
        lambda: service(db_session, student).delete_comment(room_id, comment.id),
    ):
        await assert_error(operation, "CLASSROOM_ARCHIVED")


@pytest.mark.asyncio
async def test_feed_keyset_pages_include_canonical_assignments_and_pins_once_at_equal_timestamps(
    db_session,
):
    from app.models.classroom_posts import ClassroomPost
    from app.schemas.classroom_posts import PostUpdate

    teacher, student, _, room_id = await fixture(db_session)
    _, version = await make_version(db_session, teacher, status=VersionStatus.PUBLISHED)
    posts = [await post(db_session, teacher, room_id, status="PUBLISHED") for _ in range(4)]
    await service(db_session, teacher).update(room_id, posts[-1].id, PostUpdate(pinned=True))
    stamp = datetime(2026, 10, 1, tzinfo=UTC)
    async with db_session.begin():
        assignments = [
            ClassroomAssignment(
                classroom_id=room_id,
                test_version_id=version.id,
                created_by_user_id=teacher.id,
                title=f"Fictional assignment {index}",
                created_at=stamp,
                status=AssignmentStatus.ACTIVE,
            )
            for index in range(3)
        ]
        db_session.add_all(assignments)
        for item in await db_session.scalars(
            select(ClassroomPost).where(ClassroomPost.classroom_id == room_id)
        ):
            item.created_at = stamp
        await db_session.flush()
        expected = {item.id for item in assignments} | {item.id for item in posts}
    seen = []
    cursor = None
    while True:
        page = await service(db_session, student).feed(room_id, cursor=cursor, limit=2)
        seen.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen[0].id == posts[-1].id
    assert len(seen) == len(expected) == 7
    assert {item.id for item in seen} == expected
    assert all(item.id == item.assignment_id for item in seen if item.kind == "ASSIGNMENT_ACTIVITY")
    await assert_error(
        lambda: service(db_session, student).feed(room_id, cursor="invalid"), "INVALID_CURSOR"
    )


@pytest.mark.asyncio
async def test_published_post_resource_references_follow_section_visibility(db_session):
    from app.models.classroom_classwork import (
        ClassroomContentItem,
        ClassroomResource,
        ClassroomSection,
    )
    from app.schemas.classroom_posts import PostCreate

    teacher, student, _, room_id = await fixture(db_session)
    async with db_session.begin():
        section = ClassroomSection(
            classroom_id=room_id, title="Hidden workshop", status="DRAFT", position=0
        )
        resource = ClassroomResource(
            classroom_id=room_id,
            title="Fictional notes",
            kind="TEXT",
            body="Notes",
            status="PUBLISHED",
        )
        db_session.add_all([section, resource])
        await db_session.flush()
        session_item = ClassroomContentItem(
            classroom_id=room_id, resource_id=resource.id, section_id=section.id, position=0
        )
        db_session.add(session_item)
        await db_session.flush()
        resource_id, section_id = resource.id, section.id
    body = PostCreate(
        kind="DISCUSSION", body="Review these notes", resource_ids=[resource_id], status="PUBLISHED"
    )
    await assert_error(
        lambda: service(db_session, teacher).create(room_id, body),
        "CLASSROOM_RESOURCE_NOT_PUBLISHED",
    )
    async with db_session.begin():
        section = await db_session.get(ClassroomSection, section_id)
        section.status = "PUBLISHED"
    published = await service(db_session, teacher).create(room_id, body)
    assert (await service(db_session, student).get(room_id, published.id)).resource_ids == [
        resource_id
    ]
    async with db_session.begin():
        section.status = "DRAFT"
    assert (await service(db_session, student).get(room_id, published.id)).resource_ids == []
    assert (await service(db_session, teacher).get(room_id, published.id)).resource_ids == [
        resource_id
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_target", ["resource", "section"])
async def test_published_post_controls_and_edits_survive_hidden_resource_references(
    db_session, hidden_target
):
    from app.models.classroom_classwork import (
        ClassroomContentItem,
        ClassroomResource,
        ClassroomSection,
    )
    from app.schemas.classroom_posts import PostCreate, PostUpdate

    teacher, student, _, room_id = await fixture(db_session)
    async with db_session.begin():
        section = ClassroomSection(
            classroom_id=room_id, title="Visible workshop", status="PUBLISHED", position=0
        )
        resource = ClassroomResource(
            classroom_id=room_id,
            title="Fictional notes",
            kind="TEXT",
            body="Notes",
            status="PUBLISHED",
        )
        db_session.add_all([section, resource])
        await db_session.flush()
        db_session.add(
            ClassroomContentItem(
                classroom_id=room_id, resource_id=resource.id, section_id=section.id, position=0
            )
        )
        await db_session.flush()
        resource_id = resource.id
    published = await service(db_session, teacher).create(
        room_id,
        PostCreate(
            kind="ANNOUNCEMENT",
            body="Review the notes",
            resource_ids=[resource_id],
            status="PUBLISHED",
        ),
    )
    async with db_session.begin():
        if hidden_target == "resource":
            resource.status = "ARCHIVED"
        else:
            section.status = "DRAFT"
    for changes in (
        PostUpdate(pinned=True),
        PostUpdate(pinned=False),
        PostUpdate(locked=True),
        PostUpdate(locked=False),
        PostUpdate(title="Updated workshop", body="Updated published instructions"),
    ):
        updated = await service(db_session, teacher).update(room_id, published.id, changes)
        for field in changes.model_fields_set:
            assert getattr(updated, field) == getattr(changes, field)
        assert updated.published_at == published.published_at
        assert (await service(db_session, student).get(room_id, published.id)).resource_ids == []
    await service(db_session, teacher).publish(room_id, published.id)
    await assert_error(
        lambda: service(db_session, teacher).update(
            room_id, published.id, PostUpdate(resource_ids=[resource_id])
        ),
        "CLASSROOM_RESOURCE_NOT_PUBLISHED",
    )
    await service(db_session, teacher).update(room_id, published.id, PostUpdate(status="DRAFT"))
    await assert_error(
        lambda: service(db_session, teacher).publish(room_id, published.id),
        "CLASSROOM_RESOURCE_NOT_PUBLISHED",
    )
    async with db_session.begin():
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.entity_id == published.id)
            )
            == 1
        )
        other_room = Classroom(teacher_id=teacher.id, name="Other fictional classroom")
        db_session.add(other_room)
        await db_session.flush()
        foreign_resource = ClassroomResource(
            classroom_id=other_room.id,
            title="Foreign notes",
            kind="TEXT",
            body="Private notes",
            status="PUBLISHED",
        )
        db_session.add(foreign_resource)
        await db_session.flush()
        foreign_id = foreign_resource.id
    await assert_error(
        lambda: service(db_session, teacher).update(
            room_id, published.id, PostUpdate(resource_ids=[foreign_id])
        ),
        "CLASSROOM_RESOURCE_NOT_FOUND",
    )


@pytest.mark.asyncio
async def test_feed_api_validates_payloads_and_paginated_comment_contract(db_session):
    teacher, student, _, room_id = await fixture(db_session)
    async with api_client(db_session, teacher) as client:
        response = await client.post(
            f"/api/v1/classrooms/{room_id}/posts",
            json={"kind": "ANNOUNCEMENT", "body": "Fictional announcement", "status": "PUBLISHED"},
        )
        assert response.status_code == 201
        post_id = response.json()["id"]
        assert (
            await client.post(
                f"/api/v1/classrooms/{room_id}/posts/{post_id}/pin", json={"pinned": True}
            )
        ).json()["pinned"] is True
        assert (
            await client.post(
                f"/api/v1/classrooms/{room_id}/posts",
                json={"kind": "ASSIGNMENT_ACTIVITY", "body": "Forbidden duplicate"},
            )
        ).status_code == 422
    async with api_client(db_session, student) as client:
        assert (await client.get(f"/api/v1/classrooms/{room_id}/feed?limit=101")).status_code == 422
        assert (
            await client.post(f"/api/v1/classrooms/{room_id}/posts/{post_id}/publish")
        ).status_code == 403
        assert (
            await client.post(
                f"/api/v1/classrooms/{room_id}/posts/{post_id}/comments", json={"body": " "}
            )
        ).status_code == 422
        created_comments = []
        for body in ("First", "Second", "Third"):
            response = await client.post(
                f"/api/v1/classrooms/{room_id}/posts/{post_id}/comments", json={"body": body}
            )
            assert response.status_code == 201
            created_comments.append(response.json())
        expected_ids = [
            item["id"]
            for item in sorted(created_comments, key=lambda item: (item["created_at"], item["id"]))
        ]
        first = (
            await client.get(f"/api/v1/classrooms/{room_id}/posts/{post_id}/comments?limit=2")
        ).json()
        assert [item["id"] for item in first["items"]] == expected_ids[:2]
        second = (
            await client.get(
                f"/api/v1/classrooms/{room_id}/posts/{post_id}/comments",
                params={"limit": 2, "cursor": first["next_cursor"]},
            )
        ).json()
        assert [item["id"] for item in second["items"]] == expected_ids[2:]
        assert second["next_cursor"] is None


@pytest.mark.asyncio
async def test_feed_batches_authors_counts_and_resource_ids(db_session):
    teacher, student, _, room_id = await fixture(db_session)
    for _ in range(8):
        await post(db_session, teacher, room_id, status="PUBLISHED")
    statements = []
    connection = db_session.bind.sync_connection

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(connection, "before_cursor_execute", count_selects)
    try:
        page = await service(db_session, student).feed(room_id)
    finally:
        event.remove(connection, "before_cursor_execute", count_selects)
    assert len(page.items) == 8
    assert 1 <= len(statements) <= 9


@pytest.mark.asyncio
async def test_feed_rechecks_visibility_when_post_is_unpublished_during_batch_loading(
    db_session, monkeypatch
):
    from sqlalchemy import update

    from app.models.classroom_posts import ClassroomPost

    teacher, student, _, room_id = await fixture(db_session)
    published = await post(db_session, teacher, room_id, status="PUBLISHED")
    learner = service(db_session, student)
    load_posts = learner.repository.posts_with_authors

    async def unpublish_before_loading(*args, **kwargs):
        await db_session.execute(
            update(ClassroomPost)
            .where(ClassroomPost.id == published.id)
            .values(status="DRAFT", body="Private draft")
        )
        return await load_posts(*args, **kwargs)

    monkeypatch.setattr(learner.repository, "posts_with_authors", unpublish_before_loading)
    assert (await learner.feed(room_id)).items == []

"""Focused API/integrity coverage for removal and canonical resource feed entries."""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.classroom_classwork import ClassroomContentItem, ClassroomResource
from app.models.classroom_posts import ClassroomComment, ClassroomPost
from tests.teacher_helpers import api_client
from tests.test_classroom_classwork import course as course
from tests.test_classroom_classwork import create_resource, create_section, endpoint


@pytest.mark.parametrize("role,allowed", [("CO_TEACHER", True), ("TEACHING_ASSISTANT", False)])
async def test_staff_removal_obeys_capabilities_and_immediate_revocation(db_session, role, allowed):
    from app.services.classroom_staff import ClassroomStaffService
    from tests.test_classroom_staff_gradebook import staff_setup

    owner, _, room, _, staff, invitation = await staff_setup(db_session, role)
    base = f"/api/v1/classrooms/{room}"
    async with api_client(db_session, owner) as client:
        first = await create_resource(client, base)
        second = await create_resource(client, base)
    async with api_client(db_session, staff) as client:
        assert (await client.delete(base + "/resources/" + first["id"])).status_code == (
            200 if allowed else 403
        )
    await ClassroomStaffService(db_session, owner).change(room, invitation.id, revoke=True)
    async with api_client(db_session, staff) as client:
        assert (await client.delete(base + "/resources/" + second["id"])).status_code in {403, 404}


async def test_delete_topic_moves_contents_and_increments_revision(db_session, course):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        topic = await create_section(client, base)
        resource = await create_resource(client, base, section_id=topic["id"])
        before = (await client.get(base + "/classwork")).json()
        response = await client.delete(base + "/sections/" + topic["id"])
        assert response.status_code == 200, response.text
        after = response.json()
        assert after["revision"] == before["revision"] + 1
        assert after["sections"] == []
        assert after["items"][0]["section_id"] is None
        assert after["resources"][0]["id"] == resource["id"]


@pytest.mark.parametrize("actor", ["student", "outsider", "admin"])
async def test_removal_requires_scoped_content_capability(db_session, course, actor):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        resource = await create_resource(client, base)
    async with api_client(db_session, course[actor]) as client:
        assert (await client.delete(base + "/resources/" + resource["id"])).status_code in {
            403,
            404,
        }


async def test_resource_delete_is_scoped_and_detaches_post_references(db_session, course):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        resource = await create_resource(client, base)
        wrong = await client.delete(endpoint(course["other_room"]) + "/resources/" + resource["id"])
        assert wrong.status_code == 404
        post = await client.post(
            base + "/posts",
            json={
                "kind": "ANNOUNCEMENT",
                "body": "Fictional reference",
                "status": "PUBLISHED",
                "resource_ids": [resource["id"]],
            },
        )
        assert post.status_code == 201
        removed = await client.delete(base + "/resources/" + resource["id"])
        assert removed.status_code == 200, removed.text
        retained = await client.get(base + "/posts/" + post.json()["id"])
        assert retained.status_code == 200
        assert retained.json()["resource_ids"] == []


async def test_unreferenced_resource_is_deleted_without_broken_placement(db_session, course):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        resource = await create_resource(client, base)
        response = await client.delete(base + "/resources/" + resource["id"])
        assert response.status_code == 200, response.text
        assert response.json()["items"] == []
    async with db_session.begin():
        assert await db_session.get(ClassroomResource, UUID(resource["id"])) is None
        assert (
            await db_session.scalar(
                select(ClassroomContentItem).where(
                    ClassroomContentItem.resource_id == UUID(resource["id"])
                )
            )
            is None
        )


@pytest.mark.parametrize("hidden_parent", [False, True])
async def test_feed_rechecks_visibility_after_selecting_resource_keys(
    db_session, course, monkeypatch, hidden_parent
):
    from app.models.classroom_classwork import ClassroomSection
    from app.services.classroom_posts import ClassroomPostService

    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        topic = await create_section(client, base)
        resource = await create_resource(client, base, section_id=topic["id"])
    service = ClassroomPostService(db_session, course["student"])
    select_keys = service.repository.feed_keys

    async def change_before_hydration(*args, **kwargs):
        keys = await select_keys(*args, **kwargs)
        assert any(str(key.id) == resource["id"] for key in keys)
        row = await db_session.get(
            ClassroomSection if hidden_parent else ClassroomResource,
            UUID(topic["id"] if hidden_parent else resource["id"]),
        )
        row.status = "DRAFT"
        await db_session.flush()
        return keys

    monkeypatch.setattr(service.repository, "feed_keys", change_before_hydration)
    assert (await service.feed(course["room"].id)).items == []


async def test_post_deletion_tombstones_comments_and_notification_links(db_session, course):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        response = await client.post(
            base + "/posts",
            json={"kind": "DISCUSSION", "body": "Fictional discussion", "status": "PUBLISHED"},
        )
        post_id = response.json()["id"]
    async with api_client(db_session, course["student"]) as client:
        assert (
            await client.post(
                base + "/posts/" + post_id + "/comments", json={"body": "Fictional comment"}
            )
        ).status_code == 201
    async with api_client(db_session, course["teacher"]) as client:
        assert (await client.delete(base + "/posts/" + post_id)).status_code == 204
        assert (await client.get(base + "/posts/" + post_id)).status_code == 404
        assert (await client.get(base + "/feed")).json()["items"] == []
    async with db_session.begin():
        assert await db_session.get(ClassroomPost, UUID(post_id)) is not None
        assert await db_session.scalar(
            select(ClassroomComment.id).where(ClassroomComment.post_id == UUID(post_id))
        )


async def test_canonical_resource_feed_respects_topic_status_and_has_stable_cursor(
    db_session, course
):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        topic = await create_section(client, base, status="DRAFT")
        hidden = await create_resource(client, base, section_id=topic["id"], title="Hidden notes")
        visible = await create_resource(client, base, title="Visible notes")
        await create_resource(client, base, status="DRAFT", title="Draft notes")
    async with api_client(db_session, course["student"]) as client:
        response = await client.get(base + "/feed?content_kind=RESOURCE_ACTIVITY&limit=1")
        assert response.status_code == 200, response.text
        assert [row["id"] for row in response.json()["items"]] == [visible["id"]]
    async with api_client(db_session, course["teacher"]) as client:
        await client.patch(base + "/sections/" + topic["id"], json={"status": "PUBLISHED"})
    async with api_client(db_session, course["student"]) as client:
        first = (await client.get(base + "/feed?content_kind=RESOURCE_ACTIVITY&limit=1")).json()
        assert first["next_cursor"]
        second = (
            await client.get(
                base + "/feed",
                params={
                    "content_kind": "RESOURCE_ACTIVITY",
                    "limit": 1,
                    "cursor": first["next_cursor"],
                },
            )
        ).json()
        assert {row["id"] for row in first["items"] + second["items"]} == {
            visible["id"],
            hidden["id"],
        }
        assert all("storage_key" not in str(row) for row in first["items"] + second["items"])


async def test_resource_activity_is_not_duplicated_by_published_announcement(db_session, course):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        resource = await create_resource(client, base)
        await client.post(
            base + "/posts",
            json={
                "kind": "ANNOUNCEMENT",
                "body": "Fictional update",
                "status": "PUBLISHED",
                "resource_ids": [resource["id"]],
            },
        )
    async with api_client(db_session, course["student"]) as client:
        page = (await client.get(base + "/feed")).json()
        assert len(page["items"]) == 1
        assert page["items"][0]["kind"] == "ANNOUNCEMENT"


async def test_archived_resource_disappears_from_default_feed(db_session, course):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        resource = await create_resource(client, base)
        await client.patch(base + "/resources/" + resource["id"], json={"status": "ARCHIVED"})
        assert (await client.get(base + "/feed")).json()["items"] == []
        archived = (await client.get(base + "/feed?status=ARCHIVED")).json()["items"]
        assert len(archived) == 1 and archived[0]["id"] == resource["id"]


async def test_resource_delete_removes_plan_reference_and_invalidates_plan_revision(
    db_session, course
):
    from app.models.classroom_learning import ClassroomLearningPlan, ClassroomLearningPlanItem

    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        resource = await create_resource(client, base)
    async with db_session.begin():
        plan = ClassroomLearningPlan(
            classroom_id=course["room"].id,
            student_id=course["student"].id,
            created_by_user_id=course["teacher"].id,
            updated_by_user_id=course["teacher"].id,
            title="Fictional learning plan",
            target_skill="READING",
            focus_area="Review",
        )
        db_session.add(plan)
        await db_session.flush()
        db_session.add(
            ClassroomLearningPlanItem(
                classroom_id=course["room"].id,
                plan_id=plan.id,
                resource_id=UUID(resource["id"]),
                position=0,
            )
        )
    async with api_client(db_session, course["teacher"]) as client:
        response = await client.delete(base + "/resources/" + resource["id"])
        assert response.status_code == 200, response.text
    async with db_session.begin():
        await db_session.refresh(plan)
        assert plan.revision == 2
        assert await db_session.get(ClassroomResource, UUID(resource["id"])) is None
        assert not (
            await db_session.scalars(
                select(ClassroomLearningPlanItem).where(
                    ClassroomLearningPlanItem.plan_id == plan.id
                )
            )
        ).all()


async def test_file_deletion_cleans_storage_only_after_safe_removal(
    db_session, course, tmp_path, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        response = await client.post(
            base + "/resources/upload",
            data={"title": "Fictional file", "status": "PUBLISHED"},
            files={"file": ("fictional.txt", b"Fictional notes", "text/plain")},
        )
        assert response.status_code == 201, response.text
        resource = response.json()
    async with db_session.begin():
        row = await db_session.get(ClassroomResource, UUID(resource["id"]))
        path = get_settings().resolved_storage_root / row.storage_key
        assert path.is_file()
    async with api_client(db_session, course["teacher"]) as client:
        assert (await client.delete(base + "/resources/" + resource["id"])).status_code == 200
    assert not path.exists()


async def test_delete_detects_stale_revision_and_archived_classroom(db_session, course):
    from app.services.classrooms import ClassroomService

    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        topic = await create_section(client, base)
        stale = await client.delete(base + "/sections/" + topic["id"] + "?expected_revision=0")
        assert (stale.status_code, stale.json()["code"]) == (409, "CLASSWORK_CHANGED")
    await ClassroomService(db_session, course["teacher"]).archive(course["room"].id)
    async with api_client(db_session, course["teacher"]) as client:
        response = await client.delete(base + "/sections/" + topic["id"])
        assert (response.status_code, response.json()["code"]) == (409, "CLASSROOM_ARCHIVED")


async def test_remove_reference_preserves_attempts_but_permanent_delete_erases_them(db_session):
    from app.models import Attempt, ClassroomAssignment
    from app.schemas.classroom_assignments import AssignmentCreate, AssignmentStart
    from app.services.classroom_assignments import ClassroomAssignmentService
    from tests.test_classroom_assignments import classroom_fixture

    owner, student, room, version = await classroom_fixture(db_session, official=True)
    assigned = await ClassroomAssignmentService(db_session, owner).create(
        room, AssignmentCreate(test_version_id=version)
    )
    started = await ClassroomAssignmentService(db_session, student).start(
        assigned.id, AssignmentStart(mode="MODULE", module="WRITING")
    )
    base = f"/api/v1/classrooms/{room}"
    async with api_client(db_session, owner) as client:
        placed = await client.post(
            base + "/items", json={"assignment_id": str(assigned.id), "section_id": None}
        )
        item = placed.json()["items"][0]
        removed = await client.delete(base + "/items/" + item["id"])
        assert removed.status_code == 200, removed.text
        assert str(assigned.id) in removed.json()["removed_assignment_ids"]
        restored = await client.post(
            base + "/items", json={"assignment_id": str(assigned.id), "section_id": None}
        )
        assert restored.json()["removed_assignment_ids"] == []
    async with db_session.begin():
        assert await db_session.get(Attempt, started.attempt_id)
        assert await db_session.get(ClassroomAssignment, assigned.id)
    async with api_client(db_session, owner) as client:
        deleted = await client.delete(base + "/assignments/" + str(assigned.id))
        assert deleted.status_code == 204, deleted.text
    async with db_session.begin():
        assert (
            await db_session.scalar(select(Attempt).where(Attempt.id == started.attempt_id)) is None
        )
        assert (
            await db_session.scalar(
                select(ClassroomAssignment).where(ClassroomAssignment.id == assigned.id)
            )
            is None
        )


async def test_canonical_delete_removes_assignment_and_placement(db_session, course):
    from app.models import ClassroomAssignment
    from tests.test_classroom_classwork import make_assignment

    assignment_id = await make_assignment(db_session, course["teacher"], course["room"])
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        placed = await client.post(
            base + "/items", json={"assignment_id": str(assignment_id), "section_id": None}
        )
        assert placed.status_code == 201
        assert (await client.delete(base + "/assignments/" + str(assignment_id))).status_code == 204
        assert (await client.get(base + "/classwork")).json()["items"] == []
    async with db_session.begin():
        assert await db_session.get(ClassroomAssignment, assignment_id) is None


async def test_deleting_a_draft_topic_does_not_publish_its_hidden_children(db_session, course):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        topic = await create_section(client, base, status="DRAFT")
        resource = await create_resource(client, base, section_id=topic["id"])
        removed = await client.delete(base + "/sections/" + topic["id"])
        assert removed.status_code == 200
        assert removed.json()["resources"][0]["status"] == "DRAFT"
    async with api_client(db_session, course["student"]) as client:
        assert (await client.get(base + "/classwork")).json()["resources"] == []
        assert (await client.get(base + "/resources/" + resource["id"])).status_code == 404

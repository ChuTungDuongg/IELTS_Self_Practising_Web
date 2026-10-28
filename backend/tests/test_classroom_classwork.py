"""Focused PostgreSQL/API coverage for private, structured classroom content."""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import ClassroomAssignment, ClassroomMembership
from app.models.classroom_classwork import ClassroomContentItem, ClassroomResource
from app.models.enums import UserRole, VersionStatus
from app.schemas.classrooms import ClassroomCreate
from app.services.classrooms import ClassroomService
from tests.teacher_helpers import api_client, make_user, make_version

pytestmark = pytest.mark.integration


@pytest.fixture
async def course(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    outsider = await make_user(db_session, UserRole.TEACHER)
    room = await ClassroomService(db_session, teacher).create(
        ClassroomCreate(name="Fictional course")
    )
    other_room = await ClassroomService(db_session, teacher).create(
        ClassroomCreate(name="Other course")
    )
    async with db_session.begin():
        db_session.add(ClassroomMembership(classroom_id=room.id, user_id=student.id))
        await db_session.flush()
    return {
        "teacher": teacher,
        "student": student,
        "outsider": outsider,
        "admin": db_session.info["current_user_identity"],
        "room": room,
        "other_room": other_room,
    }


def endpoint(room):
    return f"/api/v1/classrooms/{room.id}"


async def create_section(client, base, title="Fictional unit", status="PUBLISHED"):
    response = await client.post(f"{base}/sections", json={"title": title, "status": status})
    assert response.status_code == 201, response.text
    return response.json()


async def create_resource(
    client, base, *, section_id=None, status="PUBLISHED", title="Fictional notes"
):
    response = await client.post(
        f"{base}/resources",
        json={
            "title": title,
            "kind": "TEXT",
            "body": "Fictional lesson notes.",
            "section_id": section_id,
            "status": status,
        },
    )
    assert response.status_code == 201, response.text
    assert "storage_key" not in response.json()
    return response.json()


async def make_assignment(session, teacher, room):
    _, version = await make_version(session, teacher, status=VersionStatus.PUBLISHED)
    async with session.begin():
        assignment = ClassroomAssignment(
            classroom_id=room.id,
            test_version_id=version.id,
            created_by_user_id=teacher.id,
            title="Fictional IELTS assignment",
        )
        session.add(assignment)
        await session.flush()
        assignment_id = assignment.id
    return assignment_id


async def test_student_visibility_requires_published_resource_and_containing_section(
    db_session, course
):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        published = await create_section(client, base)
        draft = await create_section(client, base, "Draft unit", "DRAFT")
        archived = await create_section(client, base, "Archived unit", "ARCHIVED")
        visible = await create_resource(client, base, section_id=published["id"])
        unsectioned = await create_resource(client, base)
        hidden = [
            await create_resource(client, base, section_id=draft["id"]),
            await create_resource(client, base, section_id=archived["id"]),
            await create_resource(client, base, section_id=published["id"], status="DRAFT"),
            await create_resource(client, base, section_id=published["id"], status="ARCHIVED"),
        ]
        staff = (await client.get(f"{base}/classwork")).json()
        assert len(staff["sections"]) == 3 and len(staff["resources"]) == 6
    async with api_client(db_session, course["student"]) as client:
        snapshot = (await client.get(f"{base}/classwork")).json()
        assert [row["id"] for row in snapshot["sections"]] == [published["id"]]
        assert {row["id"] for row in snapshot["resources"]} == {visible["id"], unsectioned["id"]}
        assert {row["resource_id"] for row in snapshot["items"]} == {
            visible["id"],
            unsectioned["id"],
        }
        assert (await client.get(f"{base}/resources")).json()["items"] == snapshot["resources"]
        assert (await client.get(f"{base}/sections")).json()["items"] == snapshot["sections"]
        for resource in hidden:
            assert (await client.get(f"{base}/resources/{resource['id']}")).status_code == 404
    async with api_client(db_session, course["teacher"]) as client:
        assert (
            await client.patch(f"{base}/sections/{draft['id']}", json={"status": "PUBLISHED"})
        ).status_code == 200
    async with api_client(db_session, course["student"]) as client:
        assert (await client.get(f"{base}/resources/{hidden[0]['id']}")).status_code == 200
    async with api_client(db_session, course["admin"]) as client:
        snapshot = await client.get(f"{base}/classwork")
        assert snapshot.status_code == 200 and len(snapshot.json()["resources"]) == 6
        denied = await client.post(f"{base}/sections", json={"title": "Admin authored"})
        assert denied.status_code == 403 and denied.json()["code"] == "CLASSROOM_OBSERVER_READ_ONLY"
    async with api_client(db_session, course["outsider"]) as client:
        assert (await client.get(f"{base}/classwork")).status_code == 404
    async with api_client(db_session, course["student"]) as client:
        assert (
            await client.post(f"{base}/sections", json={"title": "Student authored"})
        ).status_code == 403


async def test_ordering_uses_revision_and_complete_classroom_scoped_target_ids(db_session, course):
    base, other_base = endpoint(course["room"]), endpoint(course["other_room"])
    async with api_client(db_session, course["teacher"]) as client:
        source, target = await create_section(client, base), await create_section(client, base)
        first = await create_resource(client, base, section_id=source["id"])
        peer = await create_resource(client, base, section_id=source["id"])
        last = await create_resource(client, base, section_id=target["id"])
        foreign = await create_resource(client, other_base)
        foreign_snapshot = (await client.get(f"{other_base}/classwork")).json()
        foreign_item = next(
            row for row in foreign_snapshot["items"] if row["resource_id"] == foreign["id"]
        )
        before = (await client.get(f"{base}/classwork")).json()
        revision = before["revision"]
        stale = await client.post(
            f"{base}/sections/reorder",
            json={
                "ids": [target["id"], source["id"]],
                "expected_revision": revision - 1,
            },
        )
        assert stale.status_code == 409 and stale.json()["code"] == "CLASSWORK_CHANGED"
        ordered = await client.post(
            f"{base}/sections/reorder",
            json={
                "ids": [target["id"], source["id"]],
                "expected_revision": revision,
            },
        )
        assert ordered.status_code == 200, ordered.text
        assert [row["id"] for row in ordered.json()["sections"]] == [target["id"], source["id"]]
        items = {row["resource_id"]: row for row in before["items"]}
        desired = [items[last["id"]]["id"], items[first["id"]]["id"]]
        moved = await client.post(
            f"{base}/items/reorder",
            json={
                "section_id": target["id"],
                "ids": desired,
                "expected_revision": revision + 1,
            },
        )
        assert moved.status_code == 200, moved.text
        after = moved.json()
        by_resource = {row["resource_id"]: row for row in after["items"]}
        assert [
            (by_resource[key]["section_id"], by_resource[key]["position"])
            for key in (last["id"], first["id"], peer["id"])
        ] == [
            (target["id"], 0),
            (target["id"], 1),
            (source["id"], 0),
        ]
        for ids, expected, status in (
            (desired, revision + 1, 409),
            ([items[first["id"]]["id"]], after["revision"], 422),
            (desired + [foreign_item["id"]], after["revision"], 422),
            (desired + [desired[0]], after["revision"], 422),
        ):
            invalid = await client.post(
                f"{base}/items/reorder",
                json={
                    "section_id": target["id"],
                    "ids": ids,
                    "expected_revision": expected,
                },
            )
            assert invalid.status_code == status, invalid.text
        assert (await client.get(f"{base}/classwork")).json() == after


async def test_assignment_placement_preserves_one_canonical_association_when_moving(
    db_session, course
):
    room, teacher = course["room"], course["teacher"]
    assignment_id = await make_assignment(db_session, teacher, room)
    foreign_assignment = await make_assignment(db_session, teacher, course["other_room"])
    base = endpoint(room)
    async with api_client(db_session, teacher) as client:
        source, target = await create_section(client, base), await create_section(client, base)
        source_peer = await create_resource(client, base, section_id=source["id"])
        target_peer = await create_resource(client, base, section_id=target["id"])
        first = await client.post(
            f"{base}/items", json={"section_id": source["id"], "assignment_id": str(assignment_id)}
        )
        assert first.status_code == 201, first.text
        original = next(row for row in first.json()["items"] if row["assignment_id"])
        for destination in (source["id"], target["id"]):
            moved = await client.post(
                f"{base}/items",
                json={"section_id": destination, "assignment_id": str(assignment_id)},
            )
            assert moved.status_code == 201, moved.text
            associations = [row for row in moved.json()["items"] if row["assignment_id"]]
            assert len(associations) == 1 and associations[0]["id"] == original["id"]
        final = moved.json()
        by_resource = {row["resource_id"]: row for row in final["items"] if row["resource_id"]}
        assert (
            by_resource[source_peer["id"]]["position"]
            == by_resource[target_peer["id"]]["position"]
            == 0
        )
        assert associations[0]["section_id"] == target["id"] and associations[0]["position"] == 1
        foreign = await client.post(
            f"{base}/items", json={"section_id": None, "assignment_id": str(foreign_assignment)}
        )
        assert foreign.status_code == 404
        assert (await client.get(f"{base}/classwork")).json() == final
    async with db_session.begin():
        rows = list(
            await db_session.scalars(
                select(ClassroomContentItem).where(
                    ClassroomContentItem.assignment_id == assignment_id
                )
            )
        )
        assert len(rows) == 1 and rows[0].id == UUID(original["id"])


async def test_archived_classroom_blocks_all_new_classwork_mutations_but_preserves_history(
    db_session, course, tmp_path, monkeypatch
):
    import app.services.classroom_classwork as module

    monkeypatch.setattr(
        module, "get_settings", lambda: type("Settings", (), {"resolved_storage_root": tmp_path})()
    )
    room, teacher = course["room"], course["teacher"]
    assignment_id = await make_assignment(db_session, teacher, room)
    base = endpoint(room)
    async with api_client(db_session, teacher) as client:
        section = await create_section(client, base)
        resource = await create_resource(client, base, section_id=section["id"])
        before = (await client.get(f"{base}/classwork")).json()
    await ClassroomService(db_session, course["student"]).leave(room.id)
    await ClassroomService(db_session, teacher).archive(room.id)
    mutations = [
        ("post", "/sections", {"title": "Blocked"}),
        ("patch", f"/sections/{section['id']}", {"title": "Blocked"}),
        (
            "post",
            "/sections/reorder",
            {"ids": [section["id"]], "expected_revision": before["revision"]},
        ),
        ("post", "/resources", {"title": "Blocked", "kind": "TEXT", "body": "Blocked"}),
        ("patch", f"/resources/{resource['id']}", {"title": "Blocked"}),
        ("post", "/items", {"section_id": section["id"], "assignment_id": str(assignment_id)}),
        (
            "post",
            "/items/reorder",
            {
                "section_id": section["id"],
                "ids": [before["items"][0]["id"]],
                "expected_revision": before["revision"],
            },
        ),
    ]
    async with api_client(db_session, teacher) as client:
        for method, path, payload in mutations:
            response = await client.request(method, base + path, json=payload)
            assert (
                response.status_code == 409 and response.json()["code"] == "CLASSROOM_ARCHIVED"
            ), response.text
        upload = await client.post(
            f"{base}/resources/upload",
            data={"title": "Blocked"},
            files={"file": ("lesson.pdf", b"%PDF-1.7\nfictional", "application/pdf")},
        )
        assert upload.status_code == 409 and upload.json()["code"] == "CLASSROOM_ARCHIVED"
        assert (await client.get(f"{base}/classwork")).json() == before
    assert not list(tmp_path.rglob("*.pdf"))
    async with api_client(db_session, course["student"]) as client:
        assert (await client.get(f"{base}/resources/{resource['id']}")).status_code == 200


@pytest.mark.parametrize("storage_backend", ["local", "s3", "r2"])
async def test_file_download_is_private_room_scoped_and_hidden_with_its_section(
    db_session, course, tmp_path, monkeypatch, storage_backend
):
    import app.api.v1.classroom_classwork as api_module
    import app.services.classroom_classwork as module

    if storage_backend != "local":
        import boto3
        from test_storage_configuration import cloud_settings
        from test_storage_contract import FakeS3

        from app.storage import factory

        fake_client = FakeS3()
        factory._cloud_storage.cache_clear()
        monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: fake_client)
        settings = cloud_settings(storage_backend)
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    else:
        monkeypatch.setattr(
            module,
            "get_settings",
            lambda: type("Settings", (), {"resolved_storage_root": tmp_path})(),
        )
    monkeypatch.setattr(api_module, "get_settings", module.get_settings)
    base = endpoint(course["room"])
    content = b"%PDF-1.7\nFictional learning file"
    async with api_client(db_session, course["teacher"]) as client:
        section = await create_section(client, base)
        uploaded = await client.post(
            f"{base}/resources/upload",
            data={
                "title": "Fictional lesson",
                "section_id": section["id"],
                "status": "PUBLISHED",
            },
            files={"file": ("lesson.pdf", content, "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        resource = uploaded.json()
        assert "storage_key" not in resource and resource["size_bytes"] == len(content)
        assert (
            await client.get(f"{endpoint(course['other_room'])}/resources/{resource['id']}/file")
        ).status_code == 404
        invalid = await client.patch(
            f"{base}/resources/{resource['id']}", json={"body": "Replace stored data"}
        )
        assert invalid.status_code == 422
    for role in ("student", "admin"):
        async with api_client(db_session, course[role]) as client:
            download = await client.get(f"{base}/resources/{resource['id']}/file?inline=true")
            assert download.status_code == 200 and download.content == content
            assert download.headers["cache-control"] == "private, no-store"
            assert download.headers["x-content-type-options"] == "nosniff"
            assert download.headers["content-security-policy"].startswith("sandbox;")
            assert download.headers["content-disposition"].startswith("inline;")
    async with api_client(db_session, course["outsider"]) as client:
        assert (await client.get(f"{base}/resources/{resource['id']}/file")).status_code == 404
    async with api_client(db_session, course["teacher"]) as client:
        assert (
            await client.patch(f"{base}/sections/{section['id']}", json={"status": "DRAFT"})
        ).status_code == 200
        rejected = await client.post(
            f"{base}/resources/upload",
            data={"title": "Bad PDF"},
            files={"file": ("fake.pdf", b"<html>not a PDF</html>", "application/pdf")},
        )
        assert rejected.status_code == 422
    if storage_backend == "local":
        assert len(list(tmp_path.rglob("*.pdf"))) == 1
    else:
        assert len(fake_client.objects) == 1
    async with api_client(db_session, course["student"]) as client:
        assert (await client.get(f"{base}/resources/{resource['id']}/file")).status_code == 404
        assert (await client.get(f"{base}/resources/{resource['id']}")).status_code == 404


async def test_invalid_resource_patch_returns_422_and_leaves_content_and_revision_unchanged(
    db_session, course
):
    base = endpoint(course["room"])
    async with api_client(db_session, course["teacher"]) as client:
        resource = await create_resource(client, base)
        before = (await client.get(f"{base}/classwork")).json()
        for patch in (
            {"body": None},
            {"url": "https://example.com/lesson"},
            {"status": None},
            {"title": None},
        ):
            response = await client.patch(f"{base}/resources/{resource['id']}", json=patch)
            assert response.status_code == 422, response.text
        assert (await client.get(f"{base}/classwork")).json() == before


async def test_database_enforces_single_target_uniqueness_and_same_classroom_foreign_keys(
    db_session, course
):
    room, other_room, teacher = course["room"], course["other_room"], course["teacher"]
    assignment_id = await make_assignment(db_session, teacher, room)
    foreign_assignment = await make_assignment(db_session, teacher, other_room)
    base = endpoint(room)
    async with api_client(db_session, teacher) as client:
        section = await create_section(client, base)
        foreign_section = await create_section(client, endpoint(other_room))
        attached_resource = await create_resource(client, base)
    async with db_session.begin():
        unused = ClassroomResource(
            classroom_id=room.id, kind="TEXT", title="Unused", body="Fictional", status="PUBLISHED"
        )
        foreign = ClassroomResource(
            classroom_id=other_room.id,
            kind="TEXT",
            title="Other course",
            body="Fictional",
            status="PUBLISHED",
        )
        db_session.add_all([unused, foreign])
        await db_session.flush()
        unused_id, foreign_id = unused.id, foreign.id
    invalid = [
        ({"resource_id": UUID(attached_resource["id"])}, "23505"),
        ({"resource_id": unused_id, "assignment_id": assignment_id}, "23514"),
        ({}, "23514"),
        ({"resource_id": unused_id, "position": -1}, "23514"),
        ({"resource_id": foreign_id}, "23503"),
        ({"resource_id": unused_id, "section_id": UUID(foreign_section["id"])}, "23503"),
        ({"assignment_id": foreign_assignment}, "23503"),
    ]
    for values, sqlstate in invalid:
        async with db_session.begin():
            with pytest.raises(IntegrityError) as error:
                async with db_session.begin_nested():
                    db_session.add(
                        ClassroomContentItem(
                            classroom_id=room.id,
                            **{"section_id": UUID(section["id"]), "position": 0, **values},
                        )
                    )
                    await db_session.flush()
            assert error.value.orig.sqlstate == sqlstate

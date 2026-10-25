"""Listing authorization must stay correct as the library grows."""

from datetime import UTC, datetime

from sqlalchemy import event
from teacher_helpers import api_client, make_user, make_version

from app.models import TestVersion as Version
from app.models import TestVersionModeration as Moderation
from app.models.enums import (
    ModerationScope,
    ModerationStatus,
    UserRole,
    VersionStatus,
)
from app.models.enums import TestOrigin as Origin


async def test_listing_batches_public_approvals_and_owners(db_session):
    admin = db_session.info["current_user_identity"]
    owner = await make_user(db_session, UserRole.TEACHER)
    other_owner = await make_user(db_session, UserRole.TEACHER)
    learner = await make_user(db_session)

    admin_test, _ = await make_version(
        db_session, admin, status=VersionStatus.PUBLISHED, origin=Origin.ADMIN
    )
    public_test, public_version = await make_version(
        db_session, owner, status=VersionStatus.PUBLISHED
    )
    classroom_test, classroom_version = await make_version(
        db_session, owner, status=VersionStatus.PUBLISHED
    )
    private_test, _ = await make_version(db_session, owner)
    other_test, other_version = await make_version(
        db_session, other_owner, status=VersionStatus.PUBLISHED
    )
    archived_test, archived_version = await make_version(
        db_session, owner, status=VersionStatus.PUBLISHED
    )
    async with db_session.begin():
        archived_test.archived_at = datetime.now(UTC)
        db_session.add(Version(test_id=public_test.id, version_number=2))
        db_session.add_all(
            [
                Moderation(
                    test_version_id=version.id,
                    scope=scope,
                    status=ModerationStatus.APPROVED,
                    submitted_by_user_id=test_owner.id,
                )
                for version, scope, test_owner in (
                    (public_version, ModerationScope.PUBLIC, owner),
                    (classroom_version, ModerationScope.CLASSROOM, owner),
                    (other_version, ModerationScope.PUBLIC, other_owner),
                    (archived_version, ModerationScope.PUBLIC, owner),
                )
            ]
        )

    ids = {
        name: str(test.id)
        for name, test in (
            ("admin", admin_test),
            ("public", public_test),
            ("classroom", classroom_test),
            ("private", private_test),
            ("other", other_test),
            ("archived", archived_test),
        )
    }
    public_version_id = str(public_version.id)
    owner_name = owner.display_name

    selects = []

    def count_selects(_conn, _cursor, statement, _params, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    connection = db_session.bind.sync_connection
    async with api_client(db_session, learner) as client:
        event.listen(connection, "before_cursor_execute", count_selects)
        try:
            learner_response = await client.get("/api/v1/tests")
        finally:
            event.remove(connection, "before_cursor_execute", count_selects)
    assert learner_response.status_code == 200
    assert {item["id"] for item in learner_response.json()} == {
        ids["admin"],
        ids["public"],
        ids["other"],
    }
    assert len(selects) == 4, f"Listing used {len(selects)} SELECTs for six tests"
    public_summary = next(item for item in learner_response.json() if item["id"] == ids["public"])
    assert [item["id"] for item in public_summary["versions"]] == [public_version_id]
    assert public_summary["owner_display_name"] == owner_name

    async with api_client(db_session, owner) as client:
        owned = await client.get("/api/v1/tests")
        assert {item["id"] for item in owned.json()} == {
            ids["admin"],
            ids["public"],
            ids["classroom"],
            ids["private"],
            ids["other"],
        }
        public_only = await client.get("/api/v1/tests?public_only=true")
        assert {item["id"] for item in public_only.json()} == {
            ids["admin"],
            ids["public"],
            ids["other"],
        }
        archived = await client.get("/api/v1/tests?archived=true")
        assert [item["id"] for item in archived.json()] == [ids["archived"]]

    async with api_client(db_session, admin) as client:
        all_tests = await client.get("/api/v1/tests")
        assert len(all_tests.json()) == 5
        assert any(item["id"] == ids["private"] and item["versions"] for item in all_tests.json())
        archived_public = await client.get("/api/v1/tests?archived=true&public_only=true")
        assert archived_public.json() == []

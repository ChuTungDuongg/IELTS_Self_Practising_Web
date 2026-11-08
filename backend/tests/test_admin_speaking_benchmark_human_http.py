"""HTTP privacy, audio range, and scoped blind assessment tests for human rating."""

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete

from app.api.dependencies import require_admin
from app.core.database import get_session
from app.main import app
from app.models import User
from app.models.enums import UserRole
from app.models.speaking_benchmark_human import SpeakingBenchmarkRater as Rater
from app.schemas.speaking_benchmark_human import (
    AssignmentCreate,
    AssignmentRevoke,
    RaterCreate,
)
from app.services import speaking_benchmark_human as human
from app.services.speaking_benchmark import SpeakingBenchmarkService

pytestmark = pytest.mark.integration


@pytest.fixture
def http_setup(grading_lab, monkeypatch):
    factory, settings, storage, owner_id, sample_id, _ = grading_lab
    from app.core.config import get_settings

    global_settings = get_settings()
    monkeypatch.setattr(global_settings, "storage_root", settings.storage_root)
    monkeypatch.setattr(global_settings, "storage_backend", "local")
    reviewer_user = User(
        id=uuid4(),
        email=f"reviewer-{uuid4()}@example.com",
        display_name="Blind Examiner",
        role=UserRole.ADMIN,
        is_active=True,
        email_verified=True,
    )
    stranger_user = User(
        id=uuid4(),
        email=f"stranger-{uuid4()}@example.com",
        display_name="Stranger Admin",
        role=UserRole.ADMIN,
        is_active=True,
        email_verified=True,
    )
    return factory, settings, storage, owner_id, sample_id, reviewer_user, stranger_user


@pytest.mark.asyncio
async def test_scoped_blind_reviewer_routes_and_privacy_boundary(http_setup):
    factory, settings, storage, owner_id, sample_id, reviewer, stranger = http_setup

    async with factory() as session, session.begin():
        session.add_all([reviewer, stranger])

    try:
        # Owner sets up internal rater and assignment
        async with factory() as session:
            service = SpeakingBenchmarkService(
                session, owner_id, settings=settings, storage=storage
            )
            rater = await human.create_rater(
                service,
                RaterCreate(
                    kind="INTERNAL",
                    display_name=reviewer.display_name,
                    user_id=reviewer.id,
                ),
            )
            assignment = await human.create_assignment(
                service,
                sample_id,
                AssignmentCreate(rater_id=rater.id, review_revision=1),
            )
            assignment_id = str(assignment.id)

        # Helper dependency override for a given user
        async def mock_session():
            async with factory() as s:
                yield s

        app.dependency_overrides[get_session] = mock_session

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Stranger user cannot see or access the reviewer assignment
            app.dependency_overrides[require_admin] = lambda: stranger
            res = await client.get("/api/v1/admin/speaking-benchmark/reviewer-assignments")
            assert res.status_code == 200
            assert len(res.json()["items"]) == 0

            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/reviewer-assignments/{assignment_id}"
            )
            assert res.status_code == 404

            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/reviewer-assignments/{assignment_id}/audio"
            )
            assert res.status_code == 404

            # 2. Reviewer user accesses assigned blind detail
            app.dependency_overrides[require_admin] = lambda: reviewer
            res = await client.get("/api/v1/admin/speaking-benchmark/reviewer-assignments")
            assert res.status_code == 200
            items = res.json()["items"]
            assert len(items) == 1
            assert items[0]["id"] == assignment_id

            # Blind detail must NOT leak AI scores, other raters, or owner notes
            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/reviewer-assignments/{assignment_id}"
            )
            assert res.status_code == 200
            detail = res.json()
            assert detail["id"] == assignment_id
            assert detail["sample_id"] == str(sample_id)
            assert "ai" not in detail
            assert "prediction" not in detail
            assert "other_raters" not in detail
            assert "adjudication" not in detail
            assert "owner_notes" not in detail
            assert "source_note" not in detail
            assert len(detail["questions"]) > 0

            # 3. Audio streaming endpoint returns valid audio bytes
            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/reviewer-assignments/{assignment_id}/audio"
            )
            assert res.status_code in {200, 206}
            assert len(res.content) > 0
            assert res.headers["content-type"].startswith("audio/")

            # 4. Reviewer submits blind assessment
            submit_payload = {
                "expected_revision": 0,
                "bands": {
                    "fc": 6.5,
                    "lr": 7.0,
                    "gra": 6.5,
                    "pr": 7.0,
                    "overall": 7.0,
                },
                "comments": {
                    "fc": "Good fluency",
                    "lr": "Adequate range",
                    "gra": "Some complex structures",
                    "pr": "Clear pronunciation",
                    "overall": "Solid band 7",
                },
                "independently_performed": True,
                "provenance": "external_verified_report",
                "source_reference": "Official mock test center",
            }
            res = await client.post(
                f"/api/v1/admin/speaking-benchmark/reviewer-assignments/{assignment_id}/assessments",
                json=submit_payload,
            )
            assert res.status_code == 201
            assessment = res.json()
            assert assessment["bands"]["overall"] == 7.0
            assert assessment["status"] == "SUBMITTED"

            # 5. Owner revokes assignment
            async with factory() as session:
                service = SpeakingBenchmarkService(
                    session, owner_id, settings=settings, storage=storage
                )
                await human.revoke_assignment(
                    service,
                    sample_id,
                    assignment.id,
                    AssignmentRevoke(expected_revision=assignment.revision),
                )

            # 6. Immediately after revocation, reviewer access is blocked (404)
            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/reviewer-assignments/{assignment_id}"
            )
            assert res.status_code == 404

            res = await client.get(
                f"/api/v1/admin/speaking-benchmark/reviewer-assignments/{assignment_id}/audio"
            )
            assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()
        async with factory() as session, session.begin():
            await session.execute(delete(Rater).where(Rater.owner_id == owner_id))
            await session.execute(delete(User).where(User.id.in_([reviewer.id, stranger.id])))

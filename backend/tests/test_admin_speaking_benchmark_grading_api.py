"""All P2 endpoints enforce ADMIN and owner scope, including downloads."""

from uuid import uuid4

import pytest
from teacher_helpers import api_client, make_user

from app.models.enums import UserRole

ROOT = "/api/v1/admin/speaking-benchmark"


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.TEACHER])
async def test_phase2_admin_boundary(isolated_db_session, lab_settings, role):
    user = await make_user(isolated_db_session, role)
    sample, run = uuid4(), uuid4()
    async with api_client(isolated_db_session, user) as client:
        for path in [
            "/grading-availability",
            "/reports/summary",
            "/reports/samples",
            "/reports/export.csv",
            "/reports/export.json",
            f"/samples/{sample}/grading-reviews",
            f"/samples/{sample}/grading-runs",
            f"/samples/{sample}/grading-runs/{run}",
            f"/samples/{sample}/grading-runs/{run}/comparison",
        ]:
            response = await client.get(ROOT + path)
            assert response.status_code == 403, (path, response.text)


async def test_owner_cannot_read_unknown_runs_or_comparisons(isolated_db_session, lab_settings):
    user = await make_user(isolated_db_session, UserRole.ADMIN)
    sample, run = uuid4(), uuid4()
    async with api_client(isolated_db_session, user) as client:
        for path in [
            f"/samples/{sample}/grading-reviews",
            f"/samples/{sample}/grading-runs",
            f"/samples/{sample}/grading-runs/{run}",
            f"/samples/{sample}/grading-runs/{run}/comparison",
        ]:
            assert (await client.get(ROOT + path)).status_code == 404
        result = await client.get(ROOT + "/reports/summary")
        assert result.status_code == 200, result.text
        assert result.json()["eligible_samples"] == 0


async def test_report_invalid_date_range_returns_validation_error(
    isolated_db_session, lab_settings
):
    user = await make_user(isolated_db_session, UserRole.ADMIN)
    async with api_client(isolated_db_session, user) as client:
        response = await client.get(ROOT + "/reports/summary?uploaded_from=2026-11-08T00:00:00")
        assert response.status_code == 422

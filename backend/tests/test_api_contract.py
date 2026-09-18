import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_reports_server_time() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "server_time" in response.json()


@pytest.mark.asyncio
async def test_openapi_exposes_phase_one_routes() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        document = (await client.get("/openapi.json")).json()
    paths = document["paths"]
    assert "/api/v1/tests" in paths
    assert "/api/v1/test-versions/{version_id}/publish" in paths
    assert "/api/v1/attempts/{attempt_id}/answers/{question_id}" in paths
    assert "/api/v1/history" in paths

from uuid import uuid4

import pytest
from test_admin import client as client
from test_writing_anchors import anchor_input, frozen_task

from app.api.dependencies import get_current_user
from app.main import app

PREFIX = "/api/v1/admin/writing-anchors"


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/sets"),
        ("POST", "/sets"),
        ("GET", "/tasks"),
        ("GET", "/coverage"),
        ("GET", "/anchors"),
        ("POST", f"/sets/{uuid4()}/activate"),
        ("POST", f"/sets/{uuid4()}/anchors"),
        ("GET", f"/anchors/{uuid4()}"),
        ("PATCH", f"/anchors/{uuid4()}"),
        ("DELETE", f"/anchors/{uuid4()}"),
    ],
)
async def test_all_anchor_routes_require_backend_admin(client, test_user, method, path):
    response = await client.request(method, PREFIX + path, json={})
    assert response.status_code == 401
    app.dependency_overrides[get_current_user] = lambda: test_user
    response = await client.request(method, PREFIX + path, json={})
    assert response.status_code == 403


async def test_admin_can_curate_four_labels_and_publish_next_version(client, db_session):
    app.dependency_overrides[get_current_user] = lambda: db_session.info["current_user_identity"]
    task = await frozen_task(db_session)
    created = await client.post(PREFIX + "/sets", json={"name": "Human bank"})
    assert created.status_code == 201
    set_id = created.json()["id"]
    options = await client.get(PREFIX + "/tasks", params={"search": "Fictional"})
    assert options.status_code == 200 and options.json()["items"][0]["id"] == str(task.id)
    body = anchor_input(task.id).model_dump(mode="json")
    added = await client.post(PREFIX + f"/sets/{set_id}/anchors", json=body)
    assert added.status_code == 201 and added.json()["response_text"] == body["response_text"]
    assert added.json()["human_scores"] == {"ta": 6.5, "cc": 7, "lr": 7, "gra": 7}
    anchor_id = added.json()["id"]
    listed = await client.get(PREFIX + "/anchors", params={"set_id": set_id})
    assert listed.json()["total"] == 1 and "response_text" not in listed.json()["items"][0]
    body["human_scores"]["lr"] = 6.2
    assert (await client.patch(PREFIX + f"/anchors/{anchor_id}", json=body)).status_code == 422
    body["human_scores"]["lr"] = 8
    assert (await client.patch(PREFIX + f"/anchors/{anchor_id}", json=body)).status_code == 200
    assert (await client.post(PREFIX + f"/sets/{set_id}/activate")).status_code == 200
    assert (await client.delete(PREFIX + f"/anchors/{anchor_id}")).status_code == 409
    assert (await client.get(PREFIX + f"/anchors/{anchor_id}")).json()["human_scores"]["lr"] == 8
    coverage = (await client.get(PREFIX + "/coverage")).json()
    assert coverage["production_task1"][0]["readiness"] == "PARTIAL"
    assert coverage["research_task1_ta"][0]["counts"]["6.5"] == 1
    cloned = await client.post(PREFIX + "/sets", json={"name": "Human bank"})
    assert cloned.status_code == 201 and cloned.json()["version"] == 2
    new_rows = (
        await client.get(PREFIX + "/anchors", params={"set_id": cloned.json()["id"]})
    ).json()
    assert new_rows["total"] == 1
    assert (
        await client.delete(PREFIX + "/anchors/" + new_rows["items"][0]["id"])
    ).status_code == 204


async def test_anchor_api_rejects_mutable_and_unknown_tasks(client, db_session):
    from app.models.enums import VersionStatus

    app.dependency_overrides[get_current_user] = lambda: db_session.info["current_user_identity"]
    task = await frozen_task(db_session, status=VersionStatus.DRAFT)
    set_id = (await client.post(PREFIX + "/sets", json={})).json()["id"]
    for task_id in (task.id, uuid4()):
        result = await client.post(
            PREFIX + f"/sets/{set_id}/anchors", json=anchor_input(task_id).model_dump(mode="json")
        )
        assert result.status_code == 422 and result.json()["code"] == "ANCHOR_FROZEN_TASK_REQUIRED"

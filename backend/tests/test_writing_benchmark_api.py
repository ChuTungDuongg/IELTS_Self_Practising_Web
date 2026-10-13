from uuid import uuid4

import pytest
from teacher_helpers import api_client, make_user

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.main import app
from app.models import WritingBenchmarkSample
from app.models.enums import UserRole

ROOT = "/api/v1/admin/writing-benchmark"


async def create(client, task=2):
    response = await client.post(f"{ROOT}/samples", json={"task_number": task})
    assert response.status_code == 201
    return response.json()


def patch(sample, **changes):
    return {"expected_revision": sample["revision"], **changes}


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.TEACHER])
async def test_every_authoring_action_requires_admin(db_session, role):
    actor = await make_user(db_session, role)
    async with api_client(db_session, actor) as client:
        target = f"{ROOT}/samples/{uuid4()}"
        for method, url, body in [
            ("GET", f"{ROOT}/samples?task=1", None),
            ("POST", f"{ROOT}/samples", {"task_number": 1}),
            ("GET", target, None),
            ("PATCH", target, {"expected_revision": 1}),
            ("POST", target + "/complete", {"expected_revision": 1}),
            ("DELETE", target + "?expected_revision=1", None),
        ]:
            response = await client.request(method, url, json=body)
            assert response.status_code == 403
            assert response.json()["code"] == "ADMIN_REQUIRED"


async def test_anonymous_denied(db_session):
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        app.dependency_overrides.pop(get_current_user)
        assert (await client.get(f"{ROOT}/samples?task=1")).status_code == 401


async def test_partial_draft_exact_text_and_light_list(db_session):
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        sample = await create(client)
        assert sample["status"] == "DRAFT" and sample["human_overall"] is None
        text = "  Fictional prompt 😀\r\nSecond line\n\n"
        response = await client.patch(
            f"{ROOT}/samples/{sample['id']}",
            json=patch(sample, prompt=text, human_scores={"tr": 6.5}),
        )
        saved = response.json()
        assert response.status_code == 200 and saved["prompt"] == text
        assert saved["revision"] == 2 and saved["human_scores"]["tr"] == 6.5
        assert saved["status"] == "DRAFT"
        listed = (await client.get(f"{ROOT}/samples?task=2")).json()
        assert listed[0]["code"] == "T2-001"
        assert not {"prompt", "essay", "task1_image_key"} & listed[0].keys()
        assert "task1_image_key" not in saved


@pytest.mark.parametrize("score", [6.3, 6.49, -0.5, 9.5, "NaN", "Infinity", True])
async def test_invalid_labels_are_not_rounded_or_coerced(db_session, score):
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        sample = await create(client)
        assert (
            await client.patch(
                f"{ROOT}/samples/{sample['id']}", json=patch(sample, human_scores={"tr": score})
            )
        ).status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "forged"),
        ("sequence_number", 88),
        ("task_number", 1),
        ("task1_image_key", "other.png"),
        ("human_overall", 9),
        ("status", "COMPLETE"),
    ],
)
async def test_server_fields_forbidden(db_session, field, value):
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        sample = await create(client)
        assert (
            await client.patch(
                f"{ROOT}/samples/{sample['id']}", json=patch(sample, **{field: value})
            )
        ).status_code == 422


async def test_explicit_complete_field_issues_and_task_semantics(db_session):
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        for task in (1, 2):
            sample = await create(client, task)
            response = await client.post(
                f"{ROOT}/samples/{sample['id']}/complete", json=patch(sample)
            )
            assert response.status_code == 422
            issues = response.json()["errors"]
            assert {"prompt", "essay", "human_scores." + ("ta" if task == 1 else "tr")} <= {
                i["path"] for i in issues
            }
            if task == 1:
                assert "image" in {i["path"] for i in issues}
            wrong = "tr" if task == 1 else "ta"
            assert (
                await client.patch(
                    f"{ROOT}/samples/{sample['id']}", json=patch(sample, human_scores={wrong: 6})
                )
            ).status_code == 422
        assert (
            await client.patch(
                f"{ROOT}/samples/{sample['id']}", json=patch(sample, task1_task_type="PIE_CHART")
            )
        ).status_code == 422


async def test_complete_production_rounding_invalidating_patch_and_stale_write(db_session):
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        sample = await create(client)
        url = f"{ROOT}/samples/{sample['id']}"
        saved = (
            await client.patch(
                url,
                json=patch(
                    sample,
                    prompt="Fictional question",
                    essay="Fictional essay",
                    human_scores={"tr": 6, "cc": 6, "lr": 6.5, "gra": 6.5},
                ),
            )
        ).json()
        assert saved["human_overall"] == 6.5 and saved["status"] == "DRAFT"
        complete = (await client.post(url + "/complete", json=patch(saved))).json()
        assert complete["status"] == "COMPLETE"
        assert (
            await client.patch(url, json=patch(saved, essay="Stale overwrite"))
        ).status_code == 409
        demoted = (await client.patch(url, json=patch(complete, human_scores={"cc": None}))).json()
        assert demoted["status"] == "DRAFT" and demoted["essay"] == "Fictional essay"
        assert demoted["human_overall"] is None
        assert (
            await client.delete(url, params={"expected_revision": complete["revision"]})
        ).status_code == 409
        assert (
            await client.delete(url, params={"expected_revision": demoted["revision"]})
        ).status_code == 204
        assert (await client.get(url)).status_code == 404


async def test_task1_complete_with_owned_valid_image(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    async with api_client(db_session, db_session.info["current_user_identity"]) as client:
        sample = await create(client, 1)
        key = f"benchmark/writing/task1/{sample['id']}/{uuid4().hex}.png"
        image = tmp_path / key
        image.parent.mkdir(parents=True)
        image.write_bytes(b"\x89PNG\r\n\x1a\nfictional image")
        async with db_session.begin():
            row = await db_session.get(WritingBenchmarkSample, sample["id"])
            row.task1_image_key = key
        url = f"{ROOT}/samples/{sample['id']}"
        saved = (
            await client.patch(
                url,
                json=patch(
                    sample,
                    prompt="Fictional visual",
                    essay="Fictional essay",
                    task1_task_type="PIE_CHART",
                    human_scores={"ta": 6, "cc": 6, "lr": 6, "gra": 6},
                ),
            )
        ).json()
        assert (await client.post(url + "/complete", json=patch(saved))).json()[
            "status"
        ] == "COMPLETE"

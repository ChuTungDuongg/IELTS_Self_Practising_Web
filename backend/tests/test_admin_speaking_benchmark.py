"""Private Phase 1 dataset tests: no real recording, model or paid provider."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from teacher_helpers import api_client, make_user

from app.core.config import Settings, get_settings
from app.evaluation.speaking.diarization_models import DiarizationResult, SpeakerTurn
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.models.enums import UserRole
from app.models.speaking import SpeakingMediaCleanup
from app.models.speaking_benchmark import (
    SpeakingBenchmarkJob,
    SpeakingBenchmarkReview,
)
from app.services import speaking_benchmark as service_module
from app.services.speaking_benchmark_jobs import availability, configuration
from app.services.speaking_benchmark_review import (
    initial_draft,
    manifest_for_review,
    suggest_windows,
)
from app.services.speaking_media import drain_media_cleanup
from app.storage.local import LocalAssetStorage

ROOT = "/api/v1/admin/speaking-benchmark"
BYTES = b"RIFF" + b"fictional synthetic media only" * 10


def fake_probe(path, _settings):
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "duration_ms": 60000,
        "size_bytes": path.stat().st_size,
        "format": "wav",
        "sample_rate": 16000,
        "channels": 1,
    }


def result_for(checksum=hashlib.sha256(BYTES).hexdigest()):
    turns = [
        SpeakerTurn(id=f"t{i}", speaker_id=speaker, start_ms=start, end_ms=end)
        for i, (speaker, start, end) in enumerate(
            [
                ("examiner", 0, 1000),
                ("candidate", 1200, 5000),
                ("examiner", 7000, 8000),
                ("candidate", 21000, 35000),
                ("candidate", 42000, 50000),
                ("third", 54000, 55000),
            ]
        )
    ]
    return DiarizationResult(
        source="recording.wav",
        source_sha256=checksum,
        duration_ms=60000,
        cache_key="c" * 64,
        identity={"model": "fixture"},
        regular=turns,
        exclusive=turns,
    )


def valid_draft(result):
    draft = initial_draft(result)
    draft.candidate_speaker_id, draft.candidate_confirmed = "candidate", True
    draft.roles.update(candidate="candidate", examiner="examiner", third="other")
    draft.part2_start_ms, draft.part3_start_ms, draft.boundaries_verified = 20000, 40000, True
    draft = suggest_windows(result, draft)
    for segment in draft.segments:
        segment.prompt_text, segment.prompt_verified = (
            "Fictional independently entered question",
            True,
        )
        segment.long_turn = 20000 <= segment.start_ms < 40000
        if segment.long_turn:
            segment.cue_points = ["Fictional cue point"]
    return draft


@pytest.fixture
def lab_settings(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "speaking_benchmark_execution", "local")
    monkeypatch.delenv("MODAL_TASK_ID", raising=False)
    monkeypatch.delenv("IELTS_MODAL_DATABASE_MODE", raising=False)
    monkeypatch.setattr(service_module, "probe_audio", fake_probe)
    from app.evaluation.speaking.diarization_backend import LocalDiarizer

    monkeypatch.setattr(LocalDiarizer, "audio_settings", lambda self, settings: settings)
    return settings


async def upload(client, *, code="TEST-001", content=BYTES):
    return await client.post(
        f"{ROOT}/samples",
        data={
            "metadata": json.dumps(
                {"code": code, "source_note": "Fictional test permission", "rights_confirmed": True}
            )
        },
        files={"file": ("untrusted-name.bin", content, "application/octet-stream")},
    )


async def seed_review(session, sample):
    async with session.begin():
        from app.models.speaking_benchmark import SpeakingBenchmarkSample

        row = await session.get(SpeakingBenchmarkSample, UUID(sample["id"]))
        result = result_for(row.source_sha256)
        job = SpeakingBenchmarkJob(
            sample_id=row.id,
            fingerprint="b" * 64,
            source_sha256=row.source_sha256,
            configuration=configuration(get_settings()),
            status="COMPLETED",
            stage="completed",
            progress=100,
            result=result.model_dump(mode="json"),
        )
        session.add(job)
        await session.flush()
        session.add(
            SpeakingBenchmarkReview(
                sample_id=row.id,
                revision=1,
                job_id=job.id,
                draft=initial_draft(result).model_dump(mode="json"),
            )
        )
        row.review_revision, row.status = 1, "REVIEW"
    return result


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.TEACHER])
async def test_all_lab_routes_require_admin(isolated_db_session, role, lab_settings):
    actor = await make_user(isolated_db_session, role)
    async with api_client(isolated_db_session, actor) as client:
        target = f"{ROOT}/samples/{uuid4()}"
        for method, path, body in [
            ("GET", f"{ROOT}/availability", None),
            ("GET", f"{ROOT}/samples", None),
            ("GET", target, None),
            ("GET", target + "/audio", None),
            ("GET", target + "/review", None),
            ("GET", target + "/human-labels", None),
            ("GET", target + "/jobs", None),
            ("POST", target + "/diarize", None),
            ("POST", target + "/jobs/" + str(uuid4()) + "/cancel", None),
            ("DELETE", target + "?expected_revision=1", None),
            ("POST", target + "/approve", {"expected_revision": 1}),
            ("PUT", target + "/human-labels", {"expected_revision": 0}),
        ]:
            response = await client.request(method, path, json=body)
            assert response.status_code == 403, (method, path, response.text)
        assert (await upload(client)).status_code == 403


async def test_upload_persistence_duplicate_owner_isolation_and_private_ranges(
    isolated_db_session, lab_settings
):
    owner = isolated_db_session.info["current_user_identity"]
    other = await make_user(isolated_db_session, UserRole.ADMIN)
    async with api_client(isolated_db_session, owner) as client:
        response = await upload(client)
        assert response.status_code == 201, response.text
        sample = response.json()
        assert (
            sample["status"] == "DRAFT"
            and sample["source_sha256"] == hashlib.sha256(BYTES).hexdigest()
        )
        assert not {"audio_key", "owner_id", "configuration"} & sample.keys()
        assert (await upload(client)).status_code == 409
        assert (await client.get(f"{ROOT}/samples")).json()["total"] == 1
        audio = await client.get(
            f"{ROOT}/samples/{sample['id']}/audio", headers={"Range": "bytes=5-14"}
        )
        assert audio.status_code == 206 and audio.content == BYTES[5:15]
        assert audio.headers["content-range"] == f"bytes 5-14/{len(BYTES)}"
        assert "no-store" in audio.headers["cache-control"]
        assert (
            await client.get(
                f"{ROOT}/samples/{sample['id']}/audio", headers={"Range": "bytes=99999-"}
            )
        ).status_code == 416
    async with api_client(isolated_db_session, other) as client:
        assert (await client.get(f"{ROOT}/samples")).json()["items"] == []
        for suffix in ("", "/audio", "/jobs", "/review", "/human-labels"):
            assert (await client.get(f"{ROOT}/samples/{sample['id']}{suffix}")).status_code == 404
        assert (await client.post(f"{ROOT}/samples/{sample['id']}/diarize")).status_code == 404
        assert (
            await client.put(
                f"{ROOT}/samples/{sample['id']}/human-labels", json={"expected_revision": 0}
            )
        ).status_code == 404
        # Equal bytes/code in a different private dataset do not disclose a duplicate.
        assert (await upload(client)).status_code == 201


async def test_upload_rejects_corruption_bounds_and_missing_rights(
    isolated_db_session, lab_settings, monkeypatch
):
    async with api_client(
        isolated_db_session, isolated_db_session.info["current_user_identity"]
    ) as client:
        assert (await upload(client, content=b"")).status_code == 422
        monkeypatch.setattr(lab_settings, "speaking_benchmark_max_upload_mb", 1)
        assert (await upload(client, content=b"x" * (1024**2 + 1))).status_code == 413

        def invalid(*_):
            raise BenchmarkInputError("REPLAY_AUDIO_UNREADABLE")

        monkeypatch.setattr(service_module, "probe_audio", invalid)
        assert (await upload(client, content=b"not audio")).status_code == 422
        bad = await client.post(
            f"{ROOT}/samples",
            data={
                "metadata": json.dumps(
                    {"code": "X", "source_note": "test", "rights_confirmed": False}
                )
            },
            files={"file": ("x.wav", BYTES)},
        )
        assert bad.status_code == 422
        assert not list(lab_settings.resolved_storage_root.rglob("*.wav"))


async def test_review_approval_revision_history_and_source_binding(
    isolated_db_session, lab_settings
):
    async with api_client(
        isolated_db_session, isolated_db_session.info["current_user_identity"]
    ) as client:
        sample = (await upload(client)).json()
        result = await seed_review(isolated_db_session, sample)
        target = f"{ROOT}/samples/{sample['id']}"
        assert (
            await client.post(target + "/approve", json={"expected_revision": 1})
        ).status_code == 422
        draft = valid_draft(result).model_dump(mode="json")
        saved = await client.patch(
            target + "/review", json={"expected_revision": 1, "draft": draft}
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["revision"] == 2 and saved.json()["approval_errors"] == []
        approved = await client.post(target + "/approve", json={"expected_revision": 2})
        assert approved.status_code == 200, approved.text
        frozen = approved.json()
        assert frozen["manifest"]["candidate_only_verified"] is True and frozen["revision"] == 3
        assert (
            await client.patch(target + "/review", json={"expected_revision": 2, "draft": draft})
        ).status_code == 409
        draft["segments"][0]["prompt_text"] = "A revised fictional question"
        assert (
            await client.patch(target + "/review", json={"expected_revision": 3, "draft": draft})
        ).json()["revision"] == 4
        assert (await client.get(target + "/review?revision=3")).json() == frozen
        assert (await client.get(target)).json()["status"] == "REVIEW"
        # Mutated private bytes invalidate approval even though a review had been saved.
        path = next(lab_settings.resolved_storage_root.rglob("*.wav"))
        path.write_bytes(b"changed source")
        assert (
            await client.post(target + "/approve", json={"expected_revision": 4})
        ).status_code == 409


@pytest.mark.parametrize(
    "change,error",
    [
        ("identity", "SPEAKER_NOT_VERIFIED"),
        ("parts", "PART_BOUNDARIES"),
        ("prompt", "PROMPT_CONTEXT_REQUIRED"),
        ("long_turn", "FULL_ATTEMPT"),
        ("overlap", "AMBIGUOUS"),
        ("hash", "SOURCE_CHANGED"),
        ("bounds", "PART_BOUNDARIES_INVALID"),
    ],
)
def test_replay_approval_rules_are_shared(change, error):
    result = result_for()
    draft = valid_draft(result)
    if change == "identity":
        draft.candidate_confirmed = False
    if change == "parts":
        draft.boundaries_verified = False
    if change == "prompt":
        draft.segments[0].prompt_text = " "
    if change == "long_turn":
        draft.segments[1].long_turn = False
    if change == "overlap":
        result.regular.append(
            SpeakerTurn(id="overlap", speaker_id="examiner", start_ms=2000, end_ms=2500)
        )
    if change == "hash":
        draft.source_sha256 = "a" * 64
    if change == "bounds":
        draft.part3_start_ms = 1
    with pytest.raises(BenchmarkInputError, match=error):
        manifest_for_review(result, draft, 300000)


async def test_partial_labels_exact_overall_provenance_and_concurrency(
    isolated_db_session, lab_settings
):
    async with api_client(
        isolated_db_session, isolated_db_session.info["current_user_identity"]
    ) as client:
        sample = (await upload(client)).json()
        target = f"{ROOT}/samples/{sample['id']}/human-labels"
        body = {
            "expected_revision": 0,
            "bands": {"overall": 6.5},
            "provenance": "human_examiner",
            "reference": "Fictional independent source",
            "verified": True,
        }
        saved = await client.put(target, json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json()["bands"] == {
            "fc": None,
            "lr": None,
            "gra": None,
            "pr": None,
            "overall": 6.5,
        }
        assert (await client.get(target)).json() == saved.json()
        assert (await client.put(target, json=body)).status_code == 409
        for score in (6.2, True, "6.5", -1, 10):
            assert (
                await client.put(
                    target, json={**body, "expected_revision": 1, "bands": {"fc": score}}
                )
            ).status_code == 422
        for provenance in ("unverified", "ai_prediction"):
            assert (
                await client.put(
                    target, json={**body, "expected_revision": 1, "provenance": provenance}
                )
            ).status_code == 422
        sample = (await client.get(f"{ROOT}/samples/{sample['id']}")).json()
        assert sample["label_status"] == "HUMAN_VERIFIED"


async def test_job_dedup_and_delete_cleanup_outbox(isolated_db_session, lab_settings):
    async with api_client(
        isolated_db_session, isolated_db_session.info["current_user_identity"]
    ) as client:
        sample = (await upload(client)).json()
        target = f"{ROOT}/samples/{sample['id']}"
        first = await client.post(target + "/diarize")
        second = await client.post(target + "/diarize")
        assert first.status_code == second.status_code == 202
        assert first.json()["id"] == second.json()["id"]
        cancel = await client.post(target + f"/jobs/{first.json()['id']}/cancel")
        assert cancel.json()["status"] == "CANCELLED"
        sample = (await client.get(target)).json()
        assert (
            await client.delete(target + f"?expected_revision={sample['revision']}")
        ).status_code == 204
        assert (await client.get(target + "/audio")).status_code == 404
    async with isolated_db_session.begin():
        pending = await isolated_db_session.scalar(select(SpeakingMediaCleanup))
        assert pending is not None
        pending.created_at = datetime.now(UTC) - timedelta(hours=2)
        assert (
            await isolated_db_session.scalar(select(func.count()).select_from(SpeakingBenchmarkJob))
            == 0
        )
    await drain_media_cleanup(
        isolated_db_session, storage=LocalAssetStorage(lab_settings.resolved_storage_root)
    )
    assert not list(lab_settings.resolved_storage_root.rglob("*.wav"))


def test_remote_topology_is_explicit_and_web_does_not_import_native_or_paid_libraries(monkeypatch):
    settings = Settings(_env_file=None)
    assert not availability(
        settings.model_copy(update={"speaking_benchmark_execution": "remote"})
    ).can_queue
    monkeypatch.setenv("IELTS_MODAL_DATABASE_MODE", "embedded")
    assert not availability(settings).can_queue
    root = Path(__file__).parents[2]
    for path in [
        root / "backend/app/services/speaking_benchmark.py",
        root / "backend/app/services/speaking_benchmark_jobs.py",
        root / "backend/app/api/v1/speaking_benchmark.py",
    ]:
        code = path.read_text(encoding="utf-8")
        assert not any(
            term in code
            for term in (
                "import torch",
                "import pyannote",
                "import openai",
                "import azure",
                "import modal",
            )
        )

"""Durable disposable PostgreSQL + synthetic source, never private human audio."""

import hashlib
import io
import os
import wave
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_admin_speaking_benchmark import result_for, valid_draft

from app.core.config import Settings, get_settings
from app.models import User
from app.models.enums import UserRole
from app.models.speaking import SpeakingMediaCleanup
from app.models.speaking_benchmark import (
    SpeakingBenchmarkJob,
    SpeakingBenchmarkReview,
    SpeakingBenchmarkSample,
)
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark_review import manifest_for_review
from app.storage.local import LocalAssetStorage
from testsupport.test_database import validate_test_database_url


@pytest.fixture
def lab_settings(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "speaking_benchmark_execution", "local")
    monkeypatch.delenv("MODAL_TASK_ID", raising=False)
    monkeypatch.delenv("IELTS_MODAL_DATABASE_MODE", raising=False)
    from test_admin_speaking_benchmark import fake_probe

    from app.services import speaking_benchmark as service_module

    monkeypatch.setattr(service_module, "probe_audio", fake_probe)
    from app.evaluation.speaking.diarization_backend import LocalDiarizer

    monkeypatch.setattr(LocalDiarizer, "audio_settings", lambda self, settings: settings)
    return settings


@pytest_asyncio.fixture
async def grading_lab(tmp_path):
    url = os.environ.get("P2_TEST_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit disposable test DB required")
    validate_test_database_url(url, get_settings().database_url)
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        database_url=url,
        storage_root=tmp_path,
        speaking_benchmark_grading_enabled=True,
        speaking_benchmark_grading_allow_live=True,
        speaking_azure_billing_mode="free_only",
        speaking_ai_enabled=True,
        speaking_ai_provider="openai",
        speaking_ai_model="gpt-6-luna",
        ai_writing_openai_api_key="fictional-offline-key",
    )
    owner, sample_id, job_id, run_id = (uuid4() for _ in range(4))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x10\x00" * 16000 * 60)
    content = output.getvalue()
    sha = hashlib.sha256(content).hexdigest()
    result = result_for(sha)
    draft = valid_draft(result)
    manifest = manifest_for_review(result, draft, 300000)
    key = f"benchmark/speaking/{sample_id}/synthetic.wav"
    storage = LocalAssetStorage(tmp_path)
    storage.put_stream(key, io.BytesIO(content), content_type="audio/wav", max_bytes=len(content))
    async with factory() as session, session.begin():
        session.add(
            User(
                id=owner,
                email=f"p2-{owner}@example.com",
                display_name="Fictional admin",
                role=UserRole.ADMIN,
                is_active=True,
                email_verified=True,
            )
        )
        await session.flush()
        session.add(
            SpeakingBenchmarkSample(
                id=sample_id,
                owner_id=owner,
                code="SYNTHETIC",
                audio_key=key,
                source_sha256=sha,
                mime_type="audio/wav",
                byte_size=len(content),
                duration_ms=60000,
                source_note="Synthetic test rights",
                rights_confirmed=True,
                review_revision=1,
                status="APPROVED",
            )
        )
        await session.flush()
        session.add(
            SpeakingBenchmarkJob(
                id=job_id,
                sample_id=sample_id,
                fingerprint="b" * 64,
                source_sha256=sha,
                configuration={},
                status="COMPLETED",
                stage="completed",
                progress=100,
                result=result.model_dump(mode="json"),
            )
        )
        await session.flush()
        from datetime import UTC, datetime

        digest = fingerprint([sha, result.identity, manifest.model_dump(mode="json")])
        session.add(
            SpeakingBenchmarkReview(
                sample_id=sample_id,
                revision=1,
                job_id=job_id,
                draft=draft.model_dump(mode="json"),
                manifest=manifest.model_dump(mode="json"),
                approved_by=owner,
                approved_at=datetime.now(UTC),
                fingerprint=digest,
            )
        )
        await session.flush()
        from app.services.speaking_benchmark_preflight import configuration

        config = configuration(settings, "azure_pa")
        session.add(
            SpeakingBenchmarkGradingRun(
                id=run_id,
                sample_id=sample_id,
                owner_id=owner,
                review_revision=1,
                source_sha256=sha,
                manifest_fingerprint=digest,
                config_fingerprint=fingerprint(config),
                submission_key=uuid4(),
                configuration=config,
                consent={
                    "azure_audio": True,
                    "llm_text": True,
                    "estimates_usd": {"azure_pa": 0.1, "openai": 0.1},
                    "max_estimated_cost_usd": 1,
                },
                candidate_ms=25800,
                window_count=3,
            )
        )
    try:
        yield factory, settings, storage, owner, sample_id, run_id
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(SpeakingBenchmarkSample).where(SpeakingBenchmarkSample.id == sample_id)
            )
            await session.execute(
                delete(SpeakingMediaCleanup).where(SpeakingMediaCleanup.storage_key == key)
            )
            await session.execute(delete(User).where(User.id == owner))
        await engine.dispose()

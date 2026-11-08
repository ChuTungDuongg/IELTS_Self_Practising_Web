"""Owner-scoped run admission and explicit recovery; HTTP never runs inference."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.repositories.speaking_benchmark_grading import owned_run
from app.schemas.speaking_benchmark_grading import PreflightRequest, RunDTO
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import failure
from app.services.speaking_benchmark_audio import load_approved_input
from app.services.speaking_benchmark_preflight import configuration, preflight, validate_consent


async def run_dto(session, run):
    requests = list(
        await session.scalars(
            select(Checkpoint)
            .where(Checkpoint.run_id == run.id)
            .order_by(Checkpoint.created_at, Checkpoint.id)
        )
    )
    value = RunDTO.model_validate(run)
    value.requests = [
        {
            "id": str(c.id),
            "stage": c.stage,
            "provider": c.provider,
            "attempt": c.attempt,
            "status": c.status,
            "billing_state": c.billing_state,
            "usage": c.usage or {},
            "error_code": c.error_code,
        }
        for c in requests
    ]
    value.checkpointed_scores = {
        c.result["criterion"]: c.result["score"]
        for c in requests
        if c.provider == "cpu"
        and c.stage.endswith(":score")
        and c.result
        and c.result.get("score") is not None
    }
    return value


async def submit(service, sample_id, body):
    validate_consent(body.consent, body.lexical_provider)
    request_fingerprint = fingerprint(body.model_dump(mode="json", exclude={"submission_key"}))
    async with service.session.begin():
        await service.owned(sample_id)
        previous = await service.session.scalar(
            select(Run).where(
                Run.owner_id == service.owner_id, Run.submission_key == body.submission_key
            )
        )
        if previous:
            if (
                previous.sample_id != sample_id
                or previous.review_revision != body.review_revision
                or previous.configuration["lexical_provider"] != body.lexical_provider
                or previous.consent.get("request_fingerprint") != request_fingerprint
            ):
                raise failure("SPEAKING_BENCHMARK_IDEMPOTENCY_CONFLICT", 409)
            return await run_dto(service.session, previous)
    ready = await preflight(
        service,
        sample_id,
        PreflightRequest(
            review_revision=body.review_revision, lexical_provider=body.lexical_provider
        ),
    )
    if not ready["can_queue"]:
        raise failure("SPEAKING_BENCHMARK_GRADING_UNAVAILABLE", 409)
    if body.preflight_fingerprint != ready["preflight_fingerprint"]:
        raise failure("SPEAKING_BENCHMARK_PREFLIGHT_CHANGED", 409)
    async with service.session.begin():
        sample = await service.owned(sample_id, lock=True)
        previous = await service.session.scalar(
            select(Run).where(
                Run.owner_id == service.owner_id, Run.submission_key == body.submission_key
            )
        )
        if previous:
            if (
                previous.sample_id != sample_id
                or previous.consent.get("request_fingerprint") != request_fingerprint
            ):
                raise failure("SPEAKING_BENCHMARK_IDEMPOTENCY_CONFLICT", 409)
            return await run_dto(service.session, previous)
        active = await service.session.scalar(
            select(Run.id).where(
                Run.sample_id == sample_id, Run.status.in_(["PENDING", "RUNNING", "INTERRUPTED"])
            )
        )
        if active:
            raise failure("SPEAKING_BENCHMARK_GRADING_ALREADY_ACTIVE", 409)
        _, review, manifest, _ = await load_approved_input(service, sample_id, body.review_revision)
        config = configuration(service.settings, body.lexical_provider)
        digest = fingerprint(
            [str(sample_id), body.review_revision, sample.source_sha256, review.fingerprint, config]
        )
        if digest != ready["preflight_fingerprint"]:
            raise failure("SPEAKING_BENCHMARK_PREFLIGHT_CHANGED", 409)
        run = Run(
            sample_id=sample_id,
            owner_id=service.owner_id,
            review_revision=body.review_revision,
            source_sha256=sample.source_sha256,
            manifest_fingerprint=review.fingerprint,
            config_fingerprint=ready["config_fingerprint"],
            configuration=config,
            consent=body.consent.model_dump(mode="json")
            | {
                "authorized_at": datetime.now(UTC).isoformat(),
                "preflight_fingerprint": digest,
                "request_fingerprint": request_fingerprint,
            },
            submission_key=body.submission_key,
            candidate_ms=ready["candidate_ms"],
            window_count=ready["window_count"],
        )
        service.session.add(run)
        await service.session.flush()
        return await run_dto(service.session, run)


async def list_runs(service, sample_id, offset=0, limit=25):
    async with service.session.begin():
        await service.owned(sample_id)
        rows = await service.session.scalars(
            select(Run)
            .where(Run.sample_id == sample_id, Run.owner_id == service.owner_id)
            .order_by(Run.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return [await run_dto(service.session, row) for row in rows]


async def detail(service, sample_id, run_id):
    async with service.session.begin():
        return await run_dto(
            service.session, await owned_run(service.session, service.owner_id, sample_id, run_id)
        )


async def cancel_in_transaction(service, sample_id, run_id):
    """Fence a run in the caller's transaction; sample lock must precede run lock."""
    await service.owned(sample_id, lock=True)
    run = await owned_run(service.session, service.owner_id, sample_id, run_id, lock=True)
    if run.status in {"PENDING", "RUNNING", "INTERRUPTED"}:
        run.status, run.stage, run.finished_at = "CANCELLED", "cancelled", datetime.now(UTC)
        run.lease_token, run.lease_expires_at = None, None
        for attempt in await service.session.scalars(
            select(Checkpoint).where(Checkpoint.run_id == run_id, Checkpoint.status == "ATTEMPTED")
        ):
            attempt.status = "INTERRUPTED_BILLING_UNKNOWN"
    return run


async def cancel(service, sample_id, run_id):
    async with service.session.begin():
        run = await cancel_in_transaction(service, sample_id, run_id)
        await service.session.flush()
        return await run_dto(service.session, run)


async def retry_interrupted(service, sample_id, run_id, body):
    async with service.session.begin():
        await service.owned(sample_id, lock=True)
        run = await owned_run(service.session, service.owner_id, sample_id, run_id, lock=True)
        if run.status not in {"INTERRUPTED", "CANCELLED"}:
            raise failure("SPEAKING_BENCHMARK_NOT_INTERRUPTED", 409)
        lexical = run.configuration["lexical_provider"]
        validate_consent(body.consent, lexical)
        if fingerprint(configuration(service.settings, lexical)) != run.config_fingerprint:
            raise failure("SPEAKING_BENCHMARK_CONFIGURATION_CHANGED", 409)
        attempt = await service.session.get(Checkpoint, body.checkpoint_id)
        if (
            not attempt
            or attempt.run_id != run_id
            or attempt.status != "INTERRUPTED_BILLING_UNKNOWN"
        ):
            raise failure("SPEAKING_BENCHMARK_RETRY_STAGE_MISMATCH", 409)
        previous = run.consent.get("reconciliations", [])
        research_origin = (
            {"research_experiment": run.consent["research_experiment"]}
            if "research_experiment" in run.consent
            else {}
        )
        if any(r["checkpoint_id"] == str(attempt.id) for r in previous):
            raise failure("SPEAKING_BENCHMARK_RETRY_CONFLICT", 409)
        if run.status == "CANCELLED":
            from uuid import uuid4

            if await service.session.scalar(
                select(Run.id).where(
                    Run.sample_id == sample_id,
                    Run.status.in_(["PENDING", "RUNNING", "INTERRUPTED"]),
                )
            ):
                raise failure("SPEAKING_BENCHMARK_GRADING_ALREADY_ACTIVE", 409)
            run = Run(
                sample_id=run.sample_id,
                owner_id=run.owner_id,
                review_revision=run.review_revision,
                source_sha256=run.source_sha256,
                manifest_fingerprint=run.manifest_fingerprint,
                config_fingerprint=run.config_fingerprint,
                configuration=run.configuration,
                submission_key=uuid4(),
                candidate_ms=run.candidate_ms,
                window_count=run.window_count,
                consent={},
                status="PENDING",
            )
            service.session.add(run)
        run.consent = (
            body.consent.model_dump(mode="json")
            | research_origin
            | {
                "reconciliations": previous
                + [
                    {
                        "checkpoint_id": str(attempt.id),
                        "stage": attempt.stage,
                        "identity": attempt.identity,
                        "reason": body.reconciliation,
                        "authorized_at": datetime.now(UTC).isoformat(),
                    }
                ]
            }
        )
        run.status, run.stage, run.error_code = "PENDING", "explicit_retry", None
        await service.session.flush()
        return await run_dto(service.session, run)

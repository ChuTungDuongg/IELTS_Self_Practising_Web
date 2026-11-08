"""Research admission and lifecycle. HTTP operations never construct providers."""

from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path

from sqlalchemy import select

from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRObservation as Observation
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRReference as Reference
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperiment as Experiment
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperimentVariant as Variant
from app.providers.speaking_asr.lexical import lexical_identity
from app.schemas.speaking_benchmark_research import (
    METRIC_PROTOCOL,
    NORMALIZATION,
    ExperimentDTO,
    VariantDTO,
)
from app.services.speaking_audio import fingerprint, normalization_identity
from app.services.speaking_benchmark import failure
from app.services.speaking_benchmark_audio import load_approved_input, materialize_approved_audio
from app.services.speaking_benchmark_jobs import availability
from app.services.speaking_benchmark_preflight import configuration as grading_configuration
from app.services.speaking_benchmark_preflight import (
    effective_settings,
    grading_availability,
    request_budget,
)
from app.services.speaking_benchmark_reports import selected_label

TERMINAL = {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}


def variant_settings(settings, config):
    chosen = effective_settings(settings, config["provider"])
    return chosen.model_copy(
        update={"speaking_azure_segmentation_silence_timeout_ms": config["silence_ms"]}
    )


def provider_configuration(settings, body, mode):
    chosen = effective_settings(settings, body.provider)
    silence = (
        body.silence_ms
        if body.silence_ms is not None
        else chosen.speaking_azure_segmentation_silence_timeout_ms
    )
    chosen = chosen.model_copy(update={"speaking_azure_segmentation_silence_timeout_ms": silence})
    return {
        "provider": body.provider,
        "silence_ms": silence,
        "identity": lexical_identity(chosen, body.provider).model_dump(mode="json"),
        "normalizer": normalization_identity(chosen),
        "grading": grading_configuration(chosen, body.provider)
        if mode == "PAIRED_GRADING"
        else None,
    }


async def owned_experiment(service, experiment_id, *, lock=False):
    query = select(Experiment).where(
        Experiment.id == experiment_id, Experiment.owner_id == service.owner_id
    )
    row = await service.session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
    return row


async def variants_for(session, experiment_id):
    return list(
        await session.scalars(
            select(Variant)
            .where(Variant.experiment_id == experiment_id)
            .order_by(Variant.created_at, Variant.sample_id, Variant.provider_key)
        )
    )


async def dto(session, row):
    value = ExperimentDTO.model_validate(row)
    value.variants = [VariantDTO.model_validate(v) for v in await variants_for(session, row.id)]
    return value


async def create_experiment(service, body):
    if len(body.cohort) > service.settings.speaking_benchmark_research_max_samples:
        raise failure("SPEAKING_RESEARCH_COHORT_LIMIT")
    if (
        sum(len(s.segment_ids) for s in body.cohort) * len(body.variants)
        > service.settings.speaking_benchmark_report_max_rows
    ):
        raise failure("SPEAKING_RESEARCH_REPORT_TOO_LARGE")
    async with service.session.begin():
        # Serialize idempotent creation for an owner, including concurrent submissions.
        from app.models import User

        await service.session.get(User, service.owner_id, with_for_update=True)
        previous = await service.session.scalar(
            select(Experiment).where(
                Experiment.owner_id == service.owner_id,
                Experiment.submission_key == body.submission_key,
            )
        )
        request_identity = fingerprint(body.model_dump(mode="json", exclude={"submission_key"}))
        if previous:
            if previous.configuration["request_identity"] != request_identity:
                raise failure("SPEAKING_BENCHMARK_IDEMPOTENCY_CONFLICT", 409)
            return await dto(service.session, previous)
        cohort, rows, references, labels = [], [], {}, {}
        provider_ms, requests = 0, {}
        for selection in sorted(body.cohort, key=lambda s: str(s.sample_id)):
            sample, review, manifest, _ = await load_approved_input(
                service, selection.sample_id, selection.review_revision
            )
            if body.split_policy != "MIXED" and sample.split != body.split_policy:
                raise failure("SPEAKING_RESEARCH_SPLIT_MISMATCH")
            windows = [
                s.model_dump(mode="json")
                for s in manifest.segments
                if s.id in selection.segment_ids
            ]
            if len(windows) != len(selection.segment_ids):
                raise failure("SPEAKING_RESEARCH_WINDOW_MISMATCH")
            if body.mode == "PAIRED_GRADING" and len(windows) != len(manifest.segments):
                raise failure("SPEAKING_RESEARCH_PAIRED_REQUIRES_COMPLETE_APPROVED_ATTEMPT")
            cohort.append(
                {
                    "sample_id": str(sample.id),
                    "code": sample.code,
                    "review_revision": review.revision,
                    "source_sha256": sample.source_sha256,
                    "manifest_fingerprint": review.fingerprint,
                    "split": sample.split,
                    "candidate_id": sample.candidate_id,
                    "windows": windows,
                }
            )
            for window in windows:
                reference = await service.session.scalar(
                    select(Reference)
                    .where(
                        Reference.sample_id == sample.id,
                        Reference.review_revision == review.revision,
                        Reference.segment_id == window["id"],
                        Reference.status == "VERIFIED",
                    )
                    .order_by(Reference.revision.desc())
                    .limit(1)
                )
                references[f"{sample.id}:{window['id']}"] = str(reference.id) if reference else None
            label = await selected_label(service.session, sample.id)
            labels[str(sample.id)] = label.revision if label and label.verified else None
            for variant in body.variants:
                config = provider_configuration(service.settings, variant, body.mode)
                counts = (
                    request_budget(len(windows), variant.provider, service.settings)
                    if body.mode == "PAIRED_GRADING"
                    else {variant.provider: len(windows)}
                )
                for p, count in counts.items():
                    if p == "openai_typical":
                        continue
                    group = "openai" if p == "openai_maximum" else p
                    requests[group] = requests.get(group, 0) + count
                duration = sum(w["end_ms"] - w["start_ms"] for w in windows)
                provider_ms += duration * (
                    2 if body.mode == "PAIRED_GRADING" and variant.provider != "azure_pa" else 1
                )
                rows.append(
                    Variant(
                        owner_id=service.owner_id,
                        sample_id=sample.id,
                        review_revision=review.revision,
                        source_sha256=sample.source_sha256,
                        manifest_fingerprint=review.fingerprint,
                        provider_key=variant.key,
                        configuration=config,
                        fingerprint=fingerprint(
                            [
                                str(sample.id),
                                sample.source_sha256,
                                review.fingerprint,
                                windows,
                                config,
                            ]
                        ),
                        windows=windows,
                    )
                )
        if (
            provider_ms / 1000
            > min(
                body.max_provider_audio_seconds,
                service.settings.speaking_benchmark_research_max_provider_seconds,
            )
            or sum(requests.values()) > body.max_physical_requests
        ):
            raise failure("SPEAKING_RESEARCH_BUDGET_EXCEEDED")
        speaker_splits = {}
        for candidate, split in await service.session.execute(
            select(Sample.candidate_id, Sample.split).where(
                Sample.owner_id == service.owner_id,
                Sample.candidate_id != "",
                Sample.deletion_pending_at.is_(None),
            )
        ):
            speaker_splits.setdefault(candidate, set()).add(split)
        dataset_warnings = (
            ["DEV_HOLDOUT_SPEAKER_LEAKAGE"]
            if any(len(s) > 1 for s in speaker_splits.values())
            else []
        ) + (
            ["HOLDOUT_FROZEN_FINAL_EVALUATION"]
            if any(c["split"] == "HOLDOUT" for c in cohort)
            else []
        )
        config = {
            "protocol": METRIC_PROTOCOL,
            "normalization": NORMALIZATION,
            "request_identity": request_identity,
            "cohort": cohort,
            "variants": [
                r.configuration | {"key": r.provider_key} for r in rows[: len(body.variants)]
            ],
            "provider_audio_ms": provider_ms,
            "requests": requests,
            "limits": {
                "provider_audio_seconds": body.max_provider_audio_seconds,
                "physical_requests": body.max_physical_requests,
            },
            "split_policy": body.split_policy,
            "dataset_warnings": dataset_warnings,
        }
        experiment = Experiment(
            owner_id=service.owner_id,
            submission_key=body.submission_key,
            name=body.name.strip(),
            description=body.description,
            mode=body.mode,
            configuration=config,
            fingerprint=fingerprint(config),
            evaluation_selection={
                "references": references,
                "labels": labels,
                "policy": "frozen-at-creation-or-explicit-latest-verified-report",
            },
        )
        service.session.add(experiment)
        await service.session.flush()
        for row in rows:
            row.experiment_id = experiment.id
            service.session.add(row)
        await service.session.flush()
        return await dto(service.session, experiment)


def static_blockers(settings, config, mode):
    topology = availability(settings)
    reasons = [topology.reason] if not topology.can_queue else []
    if (
        not settings.speaking_benchmark_research_enabled
        or not settings.speaking_benchmark_research_allow_live
    ):
        reasons.append("SPEAKING_RESEARCH_LIVE_DISABLED")
    if not settings.speaking_asr_enabled:
        reasons.append("SPEAKING_ASR_DISABLED")
    provider = config["provider"]
    if provider.startswith("azure_") or mode == "PAIRED_GRADING":
        from app.providers.speech_analysis.azure_policy import billing_authorized

        if not settings.speaking_azure_key or not settings.speaking_azure_region:
            reasons.append("AZURE_CONFIGURATION_MISSING")
        if not billing_authorized(settings):
            reasons.append("AZURE_BILLING_NOT_AUTHORIZED")
        try:
            if find_spec("azure.cognitiveservices.speech") is None:
                reasons.append("AZURE_SDK_MISSING")
        except ModuleNotFoundError:
            reasons.append("AZURE_SDK_MISSING")
    if provider == "faster_whisper_modal":
        if (
            not settings.speaking_asr_base_url
            or not settings.ai_writing_modal_key
            or not settings.ai_writing_modal_secret
        ):
            reasons.append("MODAL_ASR_NOT_CONFIGURED")
        if not settings.speaking_lexical_asr_allow_gpu:
            reasons.append("MODAL_GPU_OPERATOR_DISABLED")
    if provider == "faster_whisper_local" and (
        not settings.speaking_asr_model_directory
        or not Path(settings.speaking_asr_model_directory).is_dir()
        or find_spec("faster_whisper") is None
    ):
        reasons.append("LOCAL_WHISPER_UNAVAILABLE")
    if provider == "faster_whisper_local" and settings.speaking_asr_model_directory:
        directory = Path(settings.speaking_asr_model_directory)
        files = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
        if not all((directory / name).is_file() for name in files):
            reasons.append("LOCAL_WHISPER_MODEL_INCOMPLETE")
        elif (
            directory / "model.bin"
        ).stat().st_size > settings.speaking_benchmark_memory_mb * 1024**2 // 3:
            reasons.append("LOCAL_WHISPER_MODEL_EXCEEDS_MEMORY_ADMISSION")
    if mode == "PAIRED_GRADING":
        selected = next(
            p for p in grading_availability(settings)["providers"] if p["provider"] == provider
        )
        reasons += selected["reasons"]
    return sorted(set(reasons))


def check_consent(experiment, consent):
    expected = set(experiment.configuration["requests"])
    if set(consent.estimates_usd) != expected or any(
        consent.estimates_usd[p] <= 0 for p in expected if p != "faster_whisper_local"
    ):
        raise failure("SPEAKING_RESEARCH_PROVIDER_ESTIMATES_REQUIRED", 409)
    if experiment.mode == "PAIRED_GRADING" and not consent.llm_text:
        raise failure("SPEAKING_RESEARCH_LLM_CONSENT_REQUIRED", 409)
    if "faster_whisper_modal" in expected and not consent.modal_gpu:
        raise failure("SPEAKING_RESEARCH_GPU_CONSENT_REQUIRED", 409)
    if (
        any(c["split"] == "HOLDOUT" for c in experiment.configuration["cohort"])
        and not consent.holdout_evaluation
    ):
        raise failure("SPEAKING_RESEARCH_HOLDOUT_CONSENT_REQUIRED", 409)


async def experiment_preflight(service, experiment_id):
    async with service.session.begin():
        experiment = await owned_experiment(service, experiment_id)
        rows = await variants_for(service.session, experiment_id)
        blockers, sources = [], []
        for row in rows:
            sample, review, manifest, _ = await load_approved_input(
                service, row.sample_id, row.review_revision
            )
            if (
                row.source_sha256 != sample.source_sha256
                or review.fingerprint != row.manifest_fingerprint
            ):
                raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
            from app.schemas.speaking_benchmark_research import ProviderVariant

            actual = provider_configuration(
                service.settings,
                ProviderVariant(
                    key=row.provider_key,
                    provider=row.configuration["provider"],
                    silence_ms=row.configuration["silence_ms"],
                ),
                experiment.mode,
            )
            if actual != row.configuration:
                blockers.append("SPEAKING_RESEARCH_CONFIGURATION_CHANGED")
            blockers += static_blockers(service.settings, row.configuration, experiment.mode)
            sources.append((sample.audio_key, manifest, sample.source_sha256))
        candidates = list(
            await service.session.execute(
                select(Sample.candidate_id, Sample.split).where(
                    Sample.owner_id == service.owner_id,
                    Sample.candidate_id != "",
                    Sample.deletion_pending_at.is_(None),
                )
            )
        )
        config, digest = experiment.configuration, experiment.fingerprint
    for key, manifest, sha in {key: (key, m, s) for key, m, s in sources}.values():
        async with materialize_approved_audio(
            service.storage, key, manifest, sha, service.settings
        ):
            pass
    splits = {}
    for candidate, split in candidates:
        splits.setdefault(candidate, set()).add(split)
    return {
        "preflight_fingerprint": digest,
        "can_start": not blockers,
        "blockers": sorted(set(blockers)),
        "requests": config["requests"],
        "provider_audio_seconds": config["provider_audio_ms"] / 1000,
        "limits": config["limits"],
        "warnings": [
            "ADMISSION_ESTIMATES_ARE_NOT_INVOICE_CAPS",
            "LIVE_ACCURACY_UNVERIFIED",
            "LLM_VARIABILITY_AND_TIMING_MAY_CONFOUND_GRADING",
        ]
        + (["DEV_HOLDOUT_SPEAKER_LEAKAGE"] if any(len(s) > 1 for s in splits.values()) else [])
        + (
            ["HOLDOUT_FROZEN_FINAL_EVALUATION"]
            if any(c["split"] == "HOLDOUT" for c in config["cohort"])
            else []
        ),
    }


async def start_experiment(service, experiment_id, body):
    ready = await experiment_preflight(service, experiment_id)
    if not ready["can_start"] or body.preflight_fingerprint != ready["preflight_fingerprint"]:
        raise failure("SPEAKING_RESEARCH_PREFLIGHT_BLOCKED", 409)
    async with service.session.begin():
        row = await owned_experiment(service, experiment_id, lock=True)
        check_consent(row, body.consent)
        if row.status != "DRAFT":
            raise failure("SPEAKING_RESEARCH_ALREADY_STARTED", 409)
        row.consent = body.consent.model_dump(mode="json") | {
            "authorized_at": datetime.now(UTC).isoformat()
        }
        row.status, row.started_at = "PENDING", datetime.now(UTC)
        if any(c["split"] == "HOLDOUT" for c in row.configuration["cohort"]):
            row.holdout_executed_at = row.started_at
        return await dto(service.session, row)


async def cancel_experiment(service, experiment_id):
    # Sample locks precede experiment/variant locks, same order as request guard.
    async with service.session.begin():
        initial = await owned_experiment(service, experiment_id)
        for c in sorted(initial.configuration["cohort"], key=lambda c: c["sample_id"]):
            from uuid import UUID

            await service.owned(UUID(c["sample_id"]), lock=True)
        from app.models.speaking_benchmark_research import (
            SpeakingBenchmarkExperimentVariant as LockedVariant,
        )

        locked_variants = list(
            await service.session.scalars(
                select(LockedVariant)
                .where(LockedVariant.experiment_id == experiment_id)
                .order_by(LockedVariant.id)
                .with_for_update()
            )
        )
        row = await owned_experiment(service, experiment_id, lock=True)
        if row.status not in TERMINAL:
            for variant in locked_variants:
                if variant.status not in TERMINAL:
                    variant.status, variant.lease_token, variant.lease_expires_at = (
                        "CANCELLED",
                        None,
                        None,
                    )
                    for observation in await service.session.scalars(
                        select(Observation).where(
                            Observation.variant_id == variant.id, Observation.status == "ATTEMPTED"
                        )
                    ):
                        observation.status = "INTERRUPTED_BILLING_UNKNOWN"
            row.status, row.finished_at = "CANCELLED", datetime.now(UTC)
        from app.services.speaking_benchmark_grading import cancel_in_transaction

        for variant in locked_variants:
            if variant.grading_run_id:
                await cancel_in_transaction(service, variant.sample_id, variant.grading_run_id)
        return await dto(service.session, row)


async def reconcile_experiment(service, experiment_id, body):
    ready = await experiment_preflight(service, experiment_id)
    if not ready["can_start"] or ready["preflight_fingerprint"] != body.preflight_fingerprint:
        raise failure("SPEAKING_RESEARCH_PREFLIGHT_BLOCKED", 409)
    async with service.session.begin():
        row = await owned_experiment(service, experiment_id, lock=True)
        check_consent(row, body.consent)
        observation = await service.session.get(Observation, body.observation_id)
        variant = (
            await service.session.get(Variant, observation.variant_id) if observation else None
        )
        if (
            not variant
            or variant.experiment_id != row.id
            or variant.owner_id != service.owner_id
            or row.status != "INTERRUPTED"
            or variant.status != "INTERRUPTED"
            or observation.status != "INTERRUPTED_BILLING_UNKNOWN"
            or observation.reconciliation
        ):
            raise failure("SPEAKING_RESEARCH_RECONCILIATION_MISMATCH", 409)
        observation.reconciliation = {
            "reason": body.reason,
            "authorized_at": datetime.now(UTC).isoformat(),
            "owner_id": str(service.owner_id),
        }
        row.consent = body.consent.model_dump(mode="json") | {
            "authorized_at": datetime.now(UTC).isoformat(),
            "previous_authorizations": row.consent.get("previous_authorizations", [])
            + [{k: v for k, v in row.consent.items() if k != "previous_authorizations"}],
        }
        variant.status, variant.error_code = "PENDING", None
        row.status = "PENDING"
        return await dto(service.session, row)


async def resume_paired(service, experiment_id, body):
    """Resume tracking only after exact P2 reconciliation via its existing endpoint."""
    ready = await experiment_preflight(service, experiment_id)
    if not ready["can_start"] or ready["preflight_fingerprint"] != body.preflight_fingerprint:
        raise failure("SPEAKING_RESEARCH_PREFLIGHT_BLOCKED", 409)
    from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run

    async with service.session.begin():
        row = await owned_experiment(service, experiment_id, lock=True)
        check_consent(row, body.consent)
        if row.status != "INTERRUPTED":
            raise failure("SPEAKING_RESEARCH_RECONCILIATION_MISMATCH", 409)
        for variant in await variants_for(service.session, row.id):
            if variant.status != "INTERRUPTED":
                continue
            if row.mode == "ASR_ONLY":
                from app.services.speaking_benchmark_research_ledger import (
                    unresolved_grading_requests,
                    unresolved_research_requests,
                )

                if await unresolved_research_requests(
                    service.session, variant.sample_id
                ) or await unresolved_grading_requests(service.session, variant.sample_id):
                    raise failure("SPEAKING_RESEARCH_RECONCILE_P2_FIRST", 409)
                variant.status, variant.error_code = "PENDING", None
                continue
            run = await service.session.get(Run, variant.grading_run_id)
            if not run or run.status == "INTERRUPTED":
                raise failure("SPEAKING_RESEARCH_RECONCILE_P2_FIRST", 409)
            variant.status, variant.error_code = "WAITING", None
        row.status = "PENDING"
        row.consent = body.consent.model_dump(mode="json") | {
            "authorized_at": datetime.now(UTC).isoformat(),
            "previous_authorizations": row.consent.get("previous_authorizations", [])
            + [{k: v for k, v in row.consent.items() if k != "previous_authorizations"}],
        }
        return await dto(service.session, row)

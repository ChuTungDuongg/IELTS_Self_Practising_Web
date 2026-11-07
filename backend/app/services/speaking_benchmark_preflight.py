"""Static readiness and approval-bound admission. Never calls provider readiness APIs."""

from app.providers.speaking_asr.lexical import (
    PROVIDERS,
    lexical_identity,
    require_lexical_permission,
)
from app.providers.speaking_llm.configured import config_identity, is_configured, transport_settings
from app.providers.speech_analysis.azure import azure_analysis_identity
from app.providers.writing_llm.base import CompletionOptions
from app.providers.writing_llm.policy import OpenAIInferencePolicy
from app.schemas.speaking_benchmark_grading import PreflightRequest
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import failure
from app.services.speaking_benchmark_audio import load_approved_input, materialize_approved_audio
from app.services.speaking_benchmark_jobs import availability
from app.services.speaking_features import feature_identity
from app.services.speaking_profile import hybrid_profile_status

PROTOCOL = "admin-speaking-evaluation-v1"


def effective_settings(settings, lexical):
    return settings.model_copy(
        update={
            "speaking_profile": "speaking_hybrid_v1",
            "speaking_asr_provider": "azure",
            "speaking_lexical_asr_provider": lexical,
        }
    )


def configuration(settings, lexical):
    chosen = effective_settings(settings, lexical)
    return {
        "version": PROTOCOL,
        "lexical_provider": lexical,
        "pa": azure_analysis_identity(chosen).model_dump(mode="json"),
        "lexical": lexical_identity(chosen, lexical).model_dump(mode="json"),
        "scorer": config_identity(chosen),
        "normalizer": chosen.speaking_normalizer_version,
        "vad_sha256": chosen.speaking_vad_model_sha256,
        "quality": chosen.speaking_quality.model_dump(mode="json"),
        "features": feature_identity(chosen),
        "max_llm_physical_requests": llm_request_maximum(chosen),
    }


def grading_availability(settings):
    topology = availability(settings)
    providers = []
    for lexical in sorted(PROVIDERS):
        chosen = effective_settings(settings, lexical)
        status = hybrid_profile_status(chosen)
        reasons = list(status["limitations"]) + list(status["lexical_asr"]["limitations"])
        if not topology.can_queue:
            reasons.append(topology.reason)
        if (
            not settings.speaking_benchmark_grading_enabled
            or not settings.speaking_benchmark_grading_allow_live
        ):
            reasons.append("SPEAKING_BENCHMARK_GRADING_DISABLED")
        if not is_configured(chosen) or config_identity(chosen)["provider"] != "openai":
            reasons.append("SPEAKING_BENCHMARK_OPENAI_NOT_CONFIGURED")
        if not status["vad_available"]:
            reasons.append("VAD_UNAVAILABLE")
        if not chosen.speaking_asr_enabled:
            reasons.append("SPEAKING_ASR_DISABLED")
        providers.append(
            {
                "provider": lexical,
                "available": not reasons,
                "reasons": sorted(set(reasons)),
                "additional_audio_request": lexical != "azure_pa",
                "gpu": lexical == "faster_whisper_modal",
            }
        )
    return {
        "can_queue": any(p["available"] for p in providers),
        "live_status": "LIVE_UNVERIFIED",
        "execution": topology.execution,
        "providers": providers,
    }


def llm_request_maximum(settings):
    policy = OpenAIInferencePolicy(transport_settings(settings))
    maximum = 0
    for criterion in ("fc", "lr", "gra", "pr"):
        for stage in ("score", "feedback"):
            resolved = policy.resolve(
                CompletionOptions(task="speaking", stage=stage, criterion=criterion)
            )
            maximum += 1 + int(resolved.repair_completion_tokens > resolved.total_completion_tokens)
            if stage == "score":
                maximum += 1  # The scorer's schema repair has no nested length retry.
    return maximum


def request_budget(windows, lexical, settings=None):
    from app.core.config import Settings

    settings = settings or Settings(_env_file=None)
    return {
        "azure_pa": windows,
        **({lexical: windows} if lexical != "azure_pa" else {}),
        "openai_typical": 8,
        "openai_maximum": llm_request_maximum(settings),
    }


def validate_consent(consent, lexical):
    providers = {"azure_pa", "openai"} | ({lexical} if lexical != "azure_pa" else set())
    if set(consent.estimates_usd) != providers or (
        lexical != "azure_pa" and not consent.independent_provider
    ):
        raise failure("SPEAKING_BENCHMARK_CONSENT_REQUIRED", 409)


async def preflight(service, sample_id, body: PreflightRequest):
    async with service.session.begin():
        sample, review, manifest, warnings = await load_approved_input(
            service, sample_id, body.review_revision
        )
        source, key, approved = sample.source_sha256, sample.audio_key, review.fingerprint
    # Verify original private bytes. No inference or normalized provider requests.
    async with materialize_approved_audio(service.storage, key, manifest, source, service.settings):
        pass
    chosen = effective_settings(service.settings, body.lexical_provider)
    for segment in manifest.segments:
        require_lexical_permission(
            chosen, body.lexical_provider, duration_ms=segment.end_ms - segment.start_ms
        )
    config = configuration(service.settings, body.lexical_provider)
    ready = grading_availability(service.settings)
    selected = next(p for p in ready["providers"] if p["provider"] == body.lexical_provider)
    candidate_ms = sum(s.end_ms - s.start_ms for s in manifest.segments)
    digest = fingerprint([str(sample_id), body.review_revision, source, approved, config])
    return {
        "preflight_fingerprint": digest,
        "config_fingerprint": fingerprint(config),
        "configuration": config,
        "review_revision": body.review_revision,
        "candidate_ms": candidate_ms,
        "window_count": len(manifest.segments),
        "parts": sorted({s.part_number for s in manifest.segments}),
        "windows": [
            {"id": s.id, "part_number": s.part_number, "start_ms": s.start_ms, "end_ms": s.end_ms}
            for s in manifest.segments
        ],
        "requests": request_budget(len(manifest.segments), body.lexical_provider, chosen),
        "warnings": warnings + ["ADMISSION_ESTIMATES_ARE_NOT_BILLING_CAPS", "LIVE_UNVERIFIED"],
        "can_queue": selected["available"],
        "blockers": selected["reasons"],
    }

"""Response-scoped speech checkpoints, independent of Luna prompts and feature versions."""

import asyncio
import hashlib
from uuid import uuid4

from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.speaking_transcript import SpeakingNormalizedAudio
from app.providers.speech_analysis.azure_policy import require_billing_authorization
from app.schemas.speech_analysis import SpeechAnalysisResult
from app.services.speaking_audio import fingerprint
from app.services.speaking_hybrid import analyze_response


async def cached_speech_analysis(
    sessions,
    audio,
    settings,
    analyzer,
    *,
    allow_interrupted_retry=False,
    cache_namespace="speech_analysis",
):
    if cache_namespace not in {"speech_analysis", "lexical_asr"}:
        raise ValueError("Unknown speech checkpoint namespace")
    require_billing_authorization(settings)
    identity = analyzer.identity.model_dump(mode="json")

    def content_hash():
        with audio.path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()

    from app.services.speaking_audio import await_audio_thread

    digest = await await_audio_thread(asyncio.to_thread(content_hash))
    key = fingerprint([audio.cache_key, digest, "segment-ms-v1", identity])

    async def locked(session):
        row = await session.scalar(
            select(SpeakingNormalizedAudio)
            .where(
                SpeakingNormalizedAudio.cache_key == audio.cache_key,
                SpeakingNormalizedAudio.source_audio_fingerprint == audio.source_audio_fingerprint,
            )
            .with_for_update()
        )
        if not row:
            raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "Normalized source is unavailable.", 409)
        return row

    previous_attempts = []
    attempt_token = str(uuid4())
    async with sessions() as session, session.begin():
        row = await locked(session)
        cache = row.metadata_json.get(cache_namespace, {})
        record = cache.get(key)
        if record and record["status"] in {"COMPLETE", "PARTIAL", "FAILED"}:
            # Partial is a terminal checkpoint, never advertised as a complete cache hit.
            return [SpeechAnalysisResult.model_validate(r) for r in record["results"]]
        if record and (not allow_interrupted_retry or record["status"] != "ATTEMPTED"):
            raise AppError(
                "SPEAKING_ANALYSIS_BILLING_UNKNOWN",
                "An interrupted speech request needs explicit operator reconciliation.",
                409,
            )
        if record:
            # Only a candidate-authorized retry can supersede an ambiguous call.
            # Retain every earlier checkpoint because its provider billing is unknown.
            previous_attempts = [
                *record.get("previous_attempts", []),
                {name: value for name, value in record.items() if name != "previous_attempts"},
            ]
        row.metadata_json = {
            **row.metadata_json,
            cache_namespace: {
                **cache,
                key: {
                    "status": "ATTEMPTED",
                    "attempt_token": attempt_token,
                    "results": [],
                    "billing": "UNKNOWN",
                    "maximum_possible_calls": audio.segment_count,
                    **({"previous_attempts": previous_attempts} if previous_attempts else {}),
                },
            },
        }

    async def checkpoint(results, status):
        async with sessions() as session, session.begin():
            row = await locked(session)
            cache = dict(row.metadata_json.get(cache_namespace, {}))
            if cache.get(key, {}).get("attempt_token") != attempt_token:
                raise AppError(
                    "SPEAKING_ANALYSIS_BILLING_UNKNOWN",
                    "This speech request was superseded by an explicitly authorized retry.",
                    409,
                )
            cache[key] = {
                "status": status,
                "attempt_token": attempt_token,
                "results": [r.model_dump(mode="json") for r in results],
                "billing": "UNKNOWN",
                "attempted_calls": sum(r.usage.attempted_calls for r in results),
                "maximum_possible_calls": audio.segment_count,
                **({"previous_attempts": previous_attempts} if previous_attempts else {}),
            }
            row.metadata_json = {**row.metadata_json, cache_namespace: cache}

    results = []

    async def observed(result):
        results.append(result)
        await checkpoint(results, "ATTEMPTED")

    result = await analyze_response(audio, settings, analyzer=analyzer, on_result=observed)
    complete = len(result) == audio.segment_count and all(r.status == "COMPLETE" for r in result)
    await checkpoint(
        result,
        "COMPLETE"
        if complete
        else "PARTIAL"
        if any(r.lexical_transcript for r in result)
        else "FAILED",
    )
    return result

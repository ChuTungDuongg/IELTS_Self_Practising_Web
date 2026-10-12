"""Small current-input summaries for attempts already authorized by the caller."""

from sqlalchemy import select

from app.models.speaking import SpeakingResponse
from app.models.speaking_ai import SpeakingAIGradingRun
from app.models.speaking_transcript import SpeakingTranscriptRun
from app.schemas.attempts import SpeakingHistorySummary
from app.services.speaking_ai import SpeakingAIService
from app.services.speaking_audio import fingerprint


async def speaking_history_summaries(session, attempt_ids):
    if not attempt_ids:
        return {}
    from app.core.config import get_settings

    identity = SpeakingAIService(session, None, get_settings()).identity
    manifests = {aid: [] for aid in attempt_ids}
    rows = await session.execute(
        select(
            SpeakingResponse.attempt_id,
            SpeakingResponse.id,
            SpeakingResponse.committed_audio_fingerprint,
        )
        .where(SpeakingResponse.attempt_id.in_(attempt_ids), SpeakingResponse.locked.is_(True))
        .order_by(SpeakingResponse.id)
    )
    for aid, rid, source in rows:
        manifests[aid].append({"response_id": str(rid), "audio_fingerprint": source})
    summaries = {aid: SpeakingHistorySummary() for aid in attempt_ids}
    transcripts = await session.execute(
        select(
            SpeakingTranscriptRun.attempt_id,
            SpeakingTranscriptRun.cache_key,
            SpeakingTranscriptRun.status,
        ).where(SpeakingTranscriptRun.attempt_id.in_(attempt_ids))
    )
    for aid, key, status in transcripts:
        if manifests[aid] and key == fingerprint([manifests[aid], identity["transcript"]]):
            summaries[aid].transcript_status = status
    grades = await session.execute(
        select(
            SpeakingAIGradingRun.attempt_id,
            SpeakingAIGradingRun.id,
            SpeakingAIGradingRun.cache_key,
            SpeakingAIGradingRun.status,
            SpeakingAIGradingRun.overall_band,
        ).where(SpeakingAIGradingRun.attempt_id.in_(attempt_ids))
    )
    for aid, run_id, key, status, band in grades:
        if manifests[aid] and key == fingerprint([manifests[aid], identity]):
            summaries[aid].ai_status, summaries[aid].ai_run_id = status, run_id
            if status == "COMPLETED" and band is not None:
                summaries[aid].advisory_overall_band = float(band)
    return summaries

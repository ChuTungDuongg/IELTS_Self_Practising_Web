from sqlalchemy import func, select

from app.models.speaking_transcript import SpeakingTranscriptEvent, SpeakingTranscriptRun


class SpeakingTranscriptRepository:
    def __init__(self, session):
        self.session = session

    async def run(self, run_id, *, lock=False):
        query = (
            select(SpeakingTranscriptRun)
            .where(SpeakingTranscriptRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def append(self, run, event_type, payload=None):
        # Caller holds the run lock, or owns the new uncommitted run.
        sequence = (
            await self.session.scalar(
                select(func.max(SpeakingTranscriptEvent.sequence)).where(
                    SpeakingTranscriptEvent.run_id == run.id
                )
            )
            or 0
        ) + 1
        event = SpeakingTranscriptEvent(
            run_id=run.id, sequence=sequence, event_type=event_type, payload=payload or {}
        )
        self.session.add(event)
        await self.session.flush()
        return event

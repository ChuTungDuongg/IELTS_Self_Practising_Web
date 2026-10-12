from sqlalchemy import func, select

from app.models.speaking_ai import SpeakingAIGradingEvent, SpeakingAIGradingRun

ACTIVE = {"PENDING", "RUNNING"}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


class SpeakingAIRepository:
    def __init__(self, session):
        self.session = session

    async def run(self, run_id, *, lock=False):
        query = (
            select(SpeakingAIGradingRun)
            .where(SpeakingAIGradingRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def append(self, run, event_type, payload=None):
        # Caller owns the new run or holds its row lock.
        sequence = (
            await self.session.scalar(
                select(func.max(SpeakingAIGradingEvent.sequence)).where(
                    SpeakingAIGradingEvent.run_id == run.id
                )
            )
            or 0
        ) + 1
        event = SpeakingAIGradingEvent(
            run_id=run.id, sequence=sequence, event_type=event_type, payload=payload or {}
        )
        self.session.add(event)
        await self.session.flush()
        return event

"""Explicit human final scoring with shared provenance authorization."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.speaking import AttemptSpeakingScore
from app.repositories.attempts import AttemptRepository
from app.schemas.grading import SpeakingFinalScore, SpeakingScoreUpdate
from app.schemas.speaking import SpeakingReviewData
from app.services.attempt_scope import AttemptScopeGuard
from app.services.grading_policy import GradingPolicy
from app.services.speaking_scorer import speaking_overall


async def present_final_score(session: AsyncSession, attempt_id: UUID) -> SpeakingFinalScore | None:
    score = await session.get(AttemptSpeakingScore, attempt_id)
    if score is None:
        return None
    criteria = {key: float(getattr(score, key)) for key in ("fc", "lr", "gra", "pr")}
    return SpeakingFinalScore.model_validate(
        {
            **criteria,
            **{f"{key}_feedback": getattr(score, f"{key}_feedback") for key in criteria},
            "overall_band": speaking_overall(criteria)[1],
        }
    )


class SpeakingFinalService:
    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor

    async def save(
        self,
        attempt_id: UUID,
        body: SpeakingScoreUpdate,
        *,
        assignment_scope: tuple[UUID, UUID] | None = None,
    ) -> SpeakingReviewData:
        async with self.session.begin():
            policy = GradingPolicy(self.session, self.actor)
            owner = self.actor.id
            if assignment_scope is not None:
                owner = await policy.require_assignment_attempt(*assignment_scope, attempt_id)
            attempt = await AttemptRepository(self.session).get(
                attempt_id, user_id=None if self.actor.role == "ADMIN" else owner, for_update=True
            )
            if attempt is None:
                raise AppError("ATTEMPT_NOT_FOUND", "Attempt not found.", 404)
            await policy.require_final(attempt, assignment_scope=assignment_scope)
            if attempt.module_type != "SPEAKING":
                raise AppError("SPEAKING_ATTEMPT_REQUIRED", "A Speaking attempt is required.", 422)
            score = await self.session.get(AttemptSpeakingScore, attempt_id)
            if score is None:
                score = AttemptSpeakingScore(attempt_id=attempt_id, **body.model_dump())
                self.session.add(score)
            else:
                for key, value in body.model_dump(exclude_unset=True).items():
                    setattr(score, key, value)
            attempt.band_score = (
                None
                if AttemptScopeGuard(attempt).focused
                else speaking_overall(body.model_dump())[1]
            )
            attempt.raw_score = None
            attempt.max_score = None
            from app.services.grading_policy import record_human_grade

            record_human_grade(self.session, attempt, self.actor, body)
            await self.session.flush()
            from app.services.speaking_media import SpeakingMediaService

            result = await SpeakingMediaService(self.session, self.actor).review(attempt_id)
            result.grading = policy.capabilities(
                attempt, has_final=True, assignment_authorized=assignment_scope is not None
            )
            return result

from sqlalchemy import select

from app.domains.profile_targets import calculate_profile_target_band
from app.models import User
from app.schemas.classroom_learning import LearningGoals
from app.services.access_policy import AccessPolicy


def present_goals(user):
    return LearningGoals(
        overall=user.target_overall_band
        if user.target_overall_band is not None
        else user.target_band,
        **{
            skill: getattr(user, f"target_{skill}_band")
            for skill in ("reading", "listening", "writing", "speaking")
        },
    )


class LearningGoalService:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor

    async def get(self):
        async with self.session.begin():
            user = await self.session.scalar(
                select(User)
                .where(User.id == self.actor.id)
                .execution_options(populate_existing=True)
            )
            return present_goals(user)

    async def save(self, data):
        async with self.session.begin():
            await AccessPolicy(self.session, self.actor).lock_actor()
            user = await self.session.get(User, self.actor.id)
            for skill in ("reading", "listening", "writing", "speaking"):
                setattr(user, f"target_{skill}_band", getattr(data, skill))
            user.target_overall_band = data.overall
            user.target_band = calculate_profile_target_band(
                user.target_listening_band,
                user.target_reading_band,
                user.target_writing_band,
                user.target_speaking_band,
            )
            await self.session.flush()
            return present_goals(user)

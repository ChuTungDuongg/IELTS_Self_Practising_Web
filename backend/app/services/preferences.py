from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserPreference
from app.schemas.preferences import PreferencesResponse, PreferencesUpdate


class PreferenceService:
    def __init__(self, session: AsyncSession, user_id: UUID):
        self.session = session
        self.user_id = user_id

    async def get(self) -> PreferencesResponse:
        async with self.session.begin():
            row = await self.session.get(UserPreference, self.user_id)
            return PreferencesResponse.model_validate(row) if row else PreferencesResponse()

    async def update(self, data: PreferencesUpdate) -> PreferencesResponse:
        values = data.model_dump(exclude_unset=True)
        async with self.session.begin():
            # Atomic insert/update also serializes simultaneous first writes. Only
            # supplied fields are updated, so concurrent partial patches compose.
            statement = (
                insert(UserPreference)
                .values(user_id=self.user_id, **values)
                .on_conflict_do_update(
                    index_elements=[UserPreference.user_id],
                    set_={**values, "updated_at": func.now()},
                )
                .returning(UserPreference)
                .execution_options(populate_existing=True)
            )
            row = (await self.session.scalars(statement)).one()
            return PreferencesResponse.model_validate(row)

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.database import get_session
from app.schemas.preferences import PreferencesResponse, PreferencesUpdate
from app.services.preferences import PreferenceService

router = APIRouter(prefix="/me/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesResponse)
async def get_preferences(user: CurrentUser, session: AsyncSession = Depends(get_session)):
    return await PreferenceService(session, user.id).get()


@router.patch("", response_model=PreferencesResponse)
async def update_preferences(
    body: PreferencesUpdate, user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await PreferenceService(session, user.id).update(body)

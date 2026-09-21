from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.test_sessions import (
    TestSessionCreate,
    TestSessionResponse,
    TestSessionStartResponse,
)
from app.services.test_sessions import TestSessionService

router = APIRouter(prefix="/test-sessions", tags=["test-sessions"])


@router.post("", response_model=TestSessionStartResponse, status_code=status.HTTP_201_CREATED)
async def start_test_session(
    body: TestSessionCreate, session: AsyncSession = Depends(get_session)
) -> TestSessionStartResponse:
    return await TestSessionService(session).start(body.test_version_id)


@router.get("/{session_id}", response_model=TestSessionResponse)
async def get_test_session(
    session_id: UUID, session: AsyncSession = Depends(get_session)
) -> TestSessionResponse:
    return await TestSessionService(session).get(session_id)


@router.post("/{session_id}/advance", response_model=TestSessionResponse)
async def advance_test_session(
    session_id: UUID, session: AsyncSession = Depends(get_session)
) -> TestSessionResponse:
    return await TestSessionService(session).advance(session_id)

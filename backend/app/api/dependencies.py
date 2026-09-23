from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.models import User
from app.models.enums import UserRole


async def get_auth_session() -> AsyncIterator[AsyncSession]:
    # A distinct dependency key keeps authentication reads out of a route service's
    # explicit transaction while retaining the same configured session factory.
    async for session in get_session():
        yield session


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_auth_session),
) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.access_cookie_name)
    authorization = request.headers.get("authorization", "")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise AppError("AUTHENTICATION_REQUIRED", "Sign in to continue.", 401)
    if not settings.jwt_secret:
        raise AppError("AUTH_NOT_CONFIGURED", "Authentication is not configured.", 503)
    claims = decode_token(
        token,
        expected_type="access",
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    user = await session.get(User, claims.subject)
    if user is None:
        raise AppError("INVALID_TOKEN", "The authentication token is invalid.", 401)
    if not user.is_active:
        raise AppError("ACCOUNT_INACTIVE", "This account is inactive.", 403)
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise AppError("ADMIN_REQUIRED", "Administrator access is required.", 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]

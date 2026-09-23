import secrets

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.schemas.auth import (
    AuthSessionResponse,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    UserResponse,
)
from app.services.auth import AuthService, IssuedSession

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(response: Response, issued: IssuedSession, settings: Settings) -> None:
    common = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
    }
    # Remove cookies created by the earlier API-only path so upgrades cannot
    # leave two same-named tokens competing on backend requests.
    response.delete_cookie(settings.access_cookie_name, path="/api/v1")
    response.delete_cookie(settings.refresh_cookie_name, path="/api/v1/auth")
    response.set_cookie(
        settings.access_cookie_name,
        issued.access_token,
        max_age=settings.access_token_minutes * 60,
        path="/",
        **common,
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        issued.refresh_token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path="/",
        **common,
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.access_cookie_name, path="/")
    response.delete_cookie(settings.refresh_cookie_name, path="/")
    response.delete_cookie(settings.access_cookie_name, path="/api/v1")
    response.delete_cookie(settings.refresh_cookie_name, path="/api/v1/auth")


def _session_response(user, issued: IssuedSession) -> AuthSessionResponse:
    return AuthSessionResponse(
        user=UserResponse.model_validate(user),
        access_expires_at=issued.access_expires_at,
    )


@router.post("/register", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthSessionResponse:
    settings = get_settings()
    service = AuthService(session, settings)
    user = await service.register(body)
    issued = await service.issue_session(user)
    _set_session_cookies(response, issued, settings)
    return _session_response(user, issued)


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthSessionResponse:
    settings = get_settings()
    service = AuthService(session, settings)
    user = await service.authenticate(str(body.email), body.password)
    issued = await service.issue_session(user)
    _set_session_cookies(response, issued, settings)
    return _session_response(user, issued)


@router.post("/refresh", response_model=AuthSessionResponse)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthSessionResponse:
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise AppError("REFRESH_REQUIRED", "The refresh session is missing.", 401)
    user, issued = await AuthService(session, settings).rotate_refresh_token(token)
    _set_session_cookies(response, issued, settings)
    return _session_response(user, issued)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> LogoutResponse:
    settings = get_settings()
    await AuthService(session, settings).revoke_refresh_token(
        request.cookies.get(settings.refresh_cookie_name)
    )
    _clear_session_cookies(response, settings)
    return LogoutResponse()


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/oauth/google/start")
async def google_start(session: AsyncSession = Depends(get_session)) -> RedirectResponse:
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    location = AuthService(session, settings).google_authorization_url(state)
    response = RedirectResponse(location, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        settings.oauth_state_cookie_name,
        state,
        max_age=600,
        path="/api/v1/auth/oauth/google/callback",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    settings = get_settings()
    expected_state = request.cookies.get(settings.oauth_state_cookie_name)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise AppError("OAUTH_STATE_INVALID", "The Google sign-in state is invalid.", 400)
    service = AuthService(session, settings)
    identity = await service.fetch_google_identity(code)
    user = await service.find_or_link_google(identity)
    issued = await service.issue_session(user)
    response = RedirectResponse(settings.frontend_origin, status_code=status.HTTP_302_FOUND)
    response.delete_cookie(
        settings.oauth_state_cookie_name, path="/api/v1/auth/oauth/google/callback"
    )
    _set_session_cookies(response, issued, settings)
    return response

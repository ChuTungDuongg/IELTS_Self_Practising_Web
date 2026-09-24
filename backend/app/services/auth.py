from __future__ import annotations

import secrets
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import (
    TokenClaims,
    create_token,
    decode_token,
    hash_password,
    token_fingerprint,
    verify_password,
)
from app.models import OAuthAccount, RefreshSession, User
from app.models.enums import OAuthProvider, UserRole
from app.schemas.auth import RegisterRequest


@dataclass(frozen=True, slots=True)
class IssuedSession:
    access_token: str
    refresh_token: str
    access_expires_at: datetime


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    subject: str
    email: str
    display_name: str
    email_verified: bool


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def register(self, data: RegisterRequest) -> User:
        email = normalize_email(str(data.email))
        async with self.session.begin():
            if await self.session.scalar(select(User.id).where(User.email == email)) is not None:
                raise AppError(
                    "EMAIL_ALREADY_REGISTERED", "An account already uses this email.", 409
                )
            user = User(
                email=email,
                display_name=data.display_name,
                password_hash=hash_password(data.password),
                role=UserRole.USER,
                is_active=True,
                email_verified=False,
            )
            self.session.add(user)
            await self.session.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        async with self.session.begin():
            user = await self.session.scalar(
                select(User).where(User.email == normalize_email(email))
            )
            if user is None or not verify_password(password, user.password_hash):
                raise AppError("INVALID_CREDENTIALS", "Email or password is incorrect.", 401)
            if not user.is_active:
                raise AppError("ACCOUNT_INACTIVE", "This account is inactive.", 403)
            user.last_login_at = datetime.now(UTC)
            await self.session.flush()
            await self.session.refresh(user)
        return user

    async def issue_session(self, user: User) -> IssuedSession:
        async with self.session.begin():
            issued = self._record_session(user)
        return issued

    def _record_session(self, user: User) -> IssuedSession:
        """Mint cookies and stage their refresh row in the caller's transaction."""
        secret = self._secret()
        now = datetime.now(UTC)
        jwt_id = secrets.token_urlsafe(32)
        access_lifetime = timedelta(minutes=self.settings.access_token_minutes)
        refresh_lifetime = timedelta(days=self.settings.refresh_token_days)
        access_token = create_token(
            subject=user.id,
            token_type="access",
            secret=secret,
            issuer=self.settings.jwt_issuer,
            audience=self.settings.jwt_audience,
            lifetime=access_lifetime,
            role=user.role.value,
            now=now,
        )
        refresh_token = create_token(
            subject=user.id,
            token_type="refresh",
            secret=secret,
            issuer=self.settings.jwt_issuer,
            audience=self.settings.jwt_audience,
            lifetime=refresh_lifetime,
            jwt_id=jwt_id,
            now=now,
        )
        self.session.add(
            RefreshSession(
                user_id=user.id,
                token_hash=token_fingerprint(jwt_id),
                expires_at=now + refresh_lifetime,
            )
        )
        return IssuedSession(access_token, refresh_token, now + access_lifetime)

    async def change_password(
        self, user_id: uuid.UUID, current_password: str, new_password: str
    ) -> tuple[User, IssuedSession]:
        async with self.session.begin():
            user = await self.session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None or not user.is_active:
                raise AppError("USER_NOT_FOUND", "The account is unavailable.", 404)
            if user.password_hash is None:
                raise AppError(
                    "PASSWORD_NOT_AVAILABLE",
                    "This account does not have a local password to change.",
                    409,
                )
            if not verify_password(current_password, user.password_hash):
                raise AppError(
                    "CURRENT_PASSWORD_INVALID", "The current password is incorrect.", 400
                )
            if new_password == current_password:
                raise AppError(
                    "PASSWORD_UNCHANGED",
                    "Choose a password different from your current password.",
                    400,
                )
            user.password_hash = hash_password(new_password)
            await self.session.execute(
                update(RefreshSession)
                .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
            issued = self._record_session(user)
            await self.session.flush()
            await self.session.refresh(user)
        return user, issued

    async def rotate_refresh_token(self, token: str) -> tuple[User, IssuedSession]:
        claims = self._decode_refresh(token)
        if not claims.jwt_id:
            raise AppError("INVALID_REFRESH_TOKEN", "The refresh session is invalid.", 401)
        now = datetime.now(UTC)
        async with self.session.begin():
            refresh = await self.session.scalar(
                select(RefreshSession)
                .where(RefreshSession.token_hash == token_fingerprint(claims.jwt_id))
                .options(selectinload(RefreshSession.user))
                .with_for_update()
            )
            if (
                refresh is None
                or refresh.user_id != claims.subject
                or refresh.revoked_at is not None
                or refresh.expires_at <= now
                or not refresh.user.is_active
            ):
                raise AppError("INVALID_REFRESH_TOKEN", "The refresh session is invalid.", 401)
            refresh.revoked_at = now
            user = refresh.user
            issued = self._record_session(user)
            await self.session.flush()
        return user, issued

    async def revoke_refresh_token(self, token: str | None) -> None:
        if not token:
            return
        try:
            claims = self._decode_refresh(token)
        except AppError:
            return
        if not claims.jwt_id:
            return
        async with self.session.begin():
            refresh = await self.session.scalar(
                select(RefreshSession)
                .where(RefreshSession.token_hash == token_fingerprint(claims.jwt_id))
                .with_for_update()
            )
            if refresh is not None and refresh.revoked_at is None:
                refresh.revoked_at = datetime.now(UTC)

    def google_authorization_url(self, state: str) -> str:
        if not self.settings.google_client_id or not self.settings.google_redirect_uri:
            raise AppError("OAUTH_NOT_CONFIGURED", "Google sign-in is not configured.", 503)
        query = urllib.parse.urlencode(
            {
                "client_id": self.settings.google_client_id,
                "redirect_uri": self.settings.google_redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "online",
                "prompt": "select_account",
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    async def fetch_google_identity(self, code: str) -> GoogleIdentity:
        if not all(
            (
                self.settings.google_client_id,
                self.settings.google_client_secret,
                self.settings.google_redirect_uri,
            )
        ):
            raise AppError("OAUTH_NOT_CONFIGURED", "Google sign-in is not configured.", 503)
        async with httpx.AsyncClient(timeout=10) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "redirect_uri": self.settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                raise AppError(
                    "OAUTH_EXCHANGE_FAILED", "Google sign-in could not be completed.", 401
                )
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise AppError(
                    "OAUTH_EXCHANGE_FAILED", "Google sign-in could not be completed.", 401
                )
            profile_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if profile_response.status_code != 200:
                raise AppError(
                    "OAUTH_PROFILE_FAILED", "Google identity could not be verified.", 401
                )
        profile = profile_response.json()
        if not profile.get("sub") or not profile.get("email"):
            raise AppError("OAUTH_PROFILE_INVALID", "Google identity is incomplete.", 401)
        return GoogleIdentity(
            subject=str(profile["sub"]),
            email=normalize_email(str(profile["email"])),
            display_name=str(profile.get("name") or profile["email"]).strip()[:160],
            email_verified=bool(profile.get("email_verified")),
        )

    async def find_or_link_google(self, identity: GoogleIdentity) -> User:
        if not identity.email_verified:
            raise AppError("OAUTH_EMAIL_UNVERIFIED", "Google has not verified this email.", 401)
        async with self.session.begin():
            account = await self.session.scalar(
                select(OAuthAccount)
                .where(
                    OAuthAccount.provider == OAuthProvider.GOOGLE,
                    OAuthAccount.provider_subject == identity.subject,
                )
                .options(selectinload(OAuthAccount.user))
            )
            if account is not None:
                user = account.user
            else:
                user = await self.session.scalar(
                    select(User).where(User.email == normalize_email(identity.email))
                )
                if user is None:
                    user = User(
                        email=normalize_email(identity.email),
                        display_name=identity.display_name,
                        password_hash=None,
                        role=UserRole.USER,
                        is_active=True,
                        email_verified=True,
                    )
                    self.session.add(user)
                    await self.session.flush()
                self.session.add(
                    OAuthAccount(
                        user_id=user.id,
                        provider=OAuthProvider.GOOGLE,
                        provider_subject=identity.subject,
                    )
                )
            if not user.is_active:
                raise AppError("ACCOUNT_INACTIVE", "This account is inactive.", 403)
            user.last_login_at = datetime.now(UTC)
            await self.session.flush()
            await self.session.refresh(user)
        return user

    def _decode_refresh(self, token: str) -> TokenClaims:
        return decode_token(
            token,
            expected_type="refresh",
            secret=self._secret(),
            issuer=self.settings.jwt_issuer,
            audience=self.settings.jwt_audience,
        )

    def _secret(self) -> str:
        if not self.settings.jwt_secret:
            raise AppError("AUTH_NOT_CONFIGURED", "Authentication is not configured.", 503)
        return self.settings.jwt_secret


def normalize_email(email: str) -> str:
    return email.strip().casefold()

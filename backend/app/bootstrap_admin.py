from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import SessionFactory
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import RegisterRequest
from app.services.auth import normalize_email


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    user_id: str
    email: str
    created: bool


async def bootstrap_admin(session: AsyncSession, settings: Settings) -> BootstrapResult:
    if not all(
        (
            settings.initial_admin_email,
            settings.initial_admin_password,
            settings.initial_admin_name,
        )
    ):
        raise AppError(
            "ADMIN_BOOTSTRAP_CONFIG_REQUIRED",
            "INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD, and INITIAL_ADMIN_NAME are required.",
            422,
        )
    if len(settings.initial_admin_password) < 12:
        raise AppError(
            "ADMIN_BOOTSTRAP_CONFIG_INVALID",
            "The initial administrator configuration is invalid.",
            422,
        )
    try:
        validated = RegisterRequest(
            email=settings.initial_admin_email,
            display_name=settings.initial_admin_name,
            password=settings.initial_admin_password,
        )
    except ValidationError as exc:
        raise AppError(
            "ADMIN_BOOTSTRAP_CONFIG_INVALID",
            "The initial administrator configuration is invalid.",
            422,
        ) from exc

    email = normalize_email(str(validated.email))
    async with session.begin():
        existing = await session.scalar(select(User).where(User.email == email).with_for_update())
        if existing is not None:
            if existing.role != UserRole.ADMIN:
                raise AppError(
                    "ADMIN_BOOTSTRAP_USER_EXISTS",
                    "A non-administrator account already uses INITIAL_ADMIN_EMAIL; no role was changed.",
                    409,
                )
            return BootstrapResult(str(existing.id), existing.email, False)
        admin = User(
            email=email,
            display_name=validated.display_name,
            password_hash=hash_password(validated.password),
            role=UserRole.ADMIN,
            is_active=True,
            email_verified=True,
        )
        session.add(admin)
        await session.flush()
        result = BootstrapResult(str(admin.id), admin.email, True)
    return result


async def _run() -> int:
    settings = get_settings()
    async with SessionFactory() as session:
        result = await bootstrap_admin(session, settings)
    state = "created" if result.created else "already exists"
    print(f"Administrator {result.email} {state}.")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_run()))
    except AppError as exc:
        print(f"Administrator bootstrap failed: {exc.message}")
        raise SystemExit(1) from None
    except ValidationError:
        print("Administrator bootstrap failed: the configuration is invalid.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

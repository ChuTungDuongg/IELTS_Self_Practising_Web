from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DevWebLocalforIELTS API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://ielts:ielts@localhost:5433/ielts"
    frontend_origin: str = "http://localhost:3000"
    storage_root: Path = Path("../storage")
    max_image_upload_mb: int = Field(default=10, gt=0)
    max_audio_upload_mb: int = Field(default=100, gt=0)
    max_transfer_zip_mb: int = Field(default=300, gt=0)
    max_transfer_uncompressed_mb: int = Field(default=600, gt=0)
    max_transfer_files: int = Field(default=5000, gt=0)
    jwt_secret: str | None = None
    jwt_issuer: str = "devweblocalforielts"
    jwt_audience: str = "devweblocalforielts-web"
    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=30, gt=0)
    access_cookie_name: str = "ielts_access"
    refresh_cookie_name: str = "ielts_refresh"
    oauth_state_cookie_name: str = "ielts_oauth_state"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    initial_admin_name: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("DATABASE_URL must point to PostgreSQL")
        return value

    @field_validator("auth_cookie_samesite")
    @classmethod
    def validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("AUTH_COOKIE_SAMESITE must be lax, strict, or none")
        return normalized

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def validate_jwt_secret(cls, value: str | None) -> str | None:
        if value in {None, ""}:
            return None
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value

    @property
    def resolved_storage_root(self) -> Path:
        root = self.storage_root
        if not root.is_absolute():
            root = Path(__file__).resolve().parents[2] / root
        return root.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()

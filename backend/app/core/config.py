from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    ai_writing_enabled: bool = False
    ai_writing_provider: str = "vllm"
    ai_writing_vllm_base_url: str = ""
    ai_writing_vllm_api_key: str = Field(default="", repr=False)
    ai_writing_vllm_model: str = "mistralai/Ministral-3-8B-Instruct-2512"
    ai_writing_modal_key: str = Field(default="", repr=False)
    ai_writing_modal_secret: str = Field(default="", repr=False)
    ai_writing_openai_api_key: str = Field(default="", repr=False)
    ai_writing_openai_model: str = "gpt-5.6-luna"
    ai_writing_openai_base_url: str = "https://api.openai.com/v1"
    ai_writing_request_timeout_seconds: float = Field(default=300, gt=0, le=900)
    ai_writing_startup_timeout_seconds: float = Field(default=600, gt=0, le=900)
    ai_writing_max_concurrent_llm_requests: int = Field(default=2, ge=1, le=4)
    ai_writing_task1_scorer: Literal["anchor_pairwise", "direct", "mts"] = "anchor_pairwise"
    ai_writing_pairwise_max_tree_nodes: int = Field(default=2, ge=1, le=3)
    ai_writing_prompt_version: str = Field(default="mts-task2-v7", min_length=1, max_length=80)
    ai_writing_chart_specialist_enabled: bool = False
    ai_writing_chart_specialist_provider: str = "deplot"
    ai_writing_deplot_model: str = "google/deplot"
    ai_writing_deplot_revision: str = "6e76d62430da16986be3426bae32301fb9115397"
    ai_writing_deplot_base_url: str = ""
    ai_writing_chart_specialist_timeout_seconds: float = Field(default=90, gt=0, le=120)
    ai_writing_stale_after_seconds: int = Field(default=90, ge=45)

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

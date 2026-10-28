from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.speaking_ai import AudioQualityConfig, PronunciationConfig


class Settings(BaseSettings):
    app_name: str = "BandPilot API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://ielts:ielts@localhost:5433/ielts"
    frontend_origin: str = "http://localhost:3000"
    storage_backend: Literal["local", "s3", "r2"] = "local"
    storage_root: Path = Path("../storage")
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_key_prefix: str = ""
    aws_access_key_id: SecretStr | None = Field(default=None, repr=False)
    aws_secret_access_key: SecretStr | None = Field(default=None, repr=False)
    aws_session_token: SecretStr | None = Field(default=None, repr=False)
    max_image_upload_mb: int = Field(default=10, gt=0)
    max_audio_upload_mb: int = Field(default=100, gt=0)
    speaking_max_chunk_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    speaking_max_response_bytes: int = Field(default=32 * 1024 * 1024, ge=1024)
    speaking_recovery_window_seconds: int = Field(default=45, ge=10, le=120)
    speaking_normalizer_version: str = Field(default="pcm-v1", min_length=1, max_length=80)
    speaking_ffmpeg_path: str = "ffmpeg"
    speaking_processing_timeout_seconds: int = Field(default=120, ge=5, le=600)
    speaking_max_decoded_seconds: int = Field(default=600, ge=1, le=1800)
    speaking_asr_enabled: bool = False
    speaking_asr_provider: Literal["local", "modal"] = "local"
    speaking_asr_base_url: str = ""
    speaking_asr_model_directory: str = ""
    speaking_asr_model: str = Field(default="local-model", min_length=1, max_length=200)
    speaking_asr_model_revision: str = Field(default="local", min_length=1, max_length=80)
    speaking_asr_version: str = Field(default="faster-whisper-v1", min_length=1, max_length=80)
    speaking_asr_language: str = Field(default="en", min_length=2, max_length=12)
    speaking_transcript_stale_seconds: int = Field(default=300, ge=60, le=1800)
    speaking_quality: AudioQualityConfig = Field(default_factory=AudioQualityConfig)
    speaking_pronunciation_enabled: bool = True
    speaking_pronunciation: PronunciationConfig = Field(default_factory=PronunciationConfig)
    speaking_ai_enabled: bool = False
    speaking_ai_provider: str | None = Field(default=None, max_length=20)
    speaking_ai_model: str | None = Field(default=None, max_length=200)
    speaking_ai_prompt_version: str = Field(
        default="speaking-score-v1", min_length=1, max_length=80
    )
    speaking_ai_rubric_version: str = Field(
        default="speaking-rubric-v1", min_length=1, max_length=80
    )
    speaking_ai_score_max_tokens: int = Field(default=192, ge=128, le=256)
    speaking_ai_feedback_max_tokens: int = Field(default=1024, ge=256, le=2048)
    speaking_ai_request_timeout_seconds: float | None = Field(
        default=None, ge=5, le=600, allow_inf_nan=False
    )
    speaking_ai_startup_timeout_seconds: float | None = Field(
        default=None, ge=5, le=1800, allow_inf_nan=False
    )
    speaking_ai_stale_seconds: int = Field(default=300, ge=60, le=1800)
    speaking_ai_transcript_wait_seconds: int = Field(default=900, ge=5, le=1800)
    speaking_ai_max_input_characters: int = Field(default=60000, ge=5000, le=200000)
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
    ai_writing_prompt_version: str = Field(default="mts-task2-v8", min_length=1, max_length=80)
    ai_writing_chart_specialist_enabled: bool = False
    ai_writing_chart_specialist_provider: str = "deplot"
    ai_writing_deplot_model: str = "google/deplot"
    ai_writing_deplot_revision: str = "6e76d62430da16986be3426bae32301fb9115397"
    ai_writing_deplot_base_url: str = ""
    ai_writing_chart_specialist_timeout_seconds: float = Field(default=90, gt=0, le=120)
    ai_writing_stale_after_seconds: int = Field(default=90, ge=45)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    @model_validator(mode="after")
    def validate_storage(self):
        if self.storage_backend == "local":
            return self
        import re

        from app.storage.keys import validate_key

        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", self.s3_bucket):
            raise ValueError("S3_BUCKET must name a bucket, without paths or URLs")
        if not self.s3_region or self.s3_region.strip() != self.s3_region:
            raise ValueError("S3_REGION is required for cloud asset storage")
        if self.s3_key_prefix:
            try:
                validate_key(self.s3_key_prefix)
            except Exception:
                raise ValueError("S3_KEY_PREFIX must be a safe relative object prefix") from None
        credentials = [
            bool(value and value.get_secret_value())
            for value in (
                self.aws_access_key_id,
                self.aws_secret_access_key,
                self.aws_session_token,
            )
        ]
        if credentials[0] != credentials[1] or (credentials[2] and not credentials[0]):
            raise ValueError("Explicit AWS credentials require both access and secret keys")
        if self.s3_endpoint_url:
            try:
                endpoint = urlsplit(self.s3_endpoint_url)
                valid = (
                    endpoint.scheme == "https"
                    and bool(endpoint.hostname)
                    and not endpoint.username
                    and not endpoint.password
                    and not endpoint.query
                    and not endpoint.fragment
                    and endpoint.path in {"", "/"}
                    and endpoint.port in {None, 443}
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(
                    "S3_ENDPOINT_URL must be an HTTPS endpoint without credentials or paths"
                )
        if self.storage_backend == "r2":
            endpoint = urlsplit(self.s3_endpoint_url)
            if (
                not endpoint.hostname
                or not endpoint.hostname.endswith(".r2.cloudflarestorage.com")
                or self.s3_region != "auto"
                or not all(credentials[:2])
            ):
                raise ValueError(
                    "R2 requires its account S3 endpoint, S3_REGION=auto and AWS access/secret keys"
                )
        elif self.s3_region == "auto":
            raise ValueError("AWS S3 requires its actual region; use STORAGE_BACKEND=r2 for R2")
        return self

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

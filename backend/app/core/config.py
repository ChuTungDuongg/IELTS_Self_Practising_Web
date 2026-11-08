from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.speaking_ai import AudioQualityConfig, PronunciationConfig


class OpenAIStageOverride(BaseModel):
    """Only explicit inference policy fields are accepted in environment JSON."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] | None = None
    total_completion_tokens: int | None = Field(default=None, ge=128, le=32768)
    timeout_seconds: float | None = Field(default=None, gt=0, le=900, allow_inf_nan=False)
    image_detail: Literal["auto", "low", "high", "original"] | None = None


class Settings(BaseSettings):
    app_name: str = "BandPilot API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://ielts:ielts@localhost:5433/ielts", repr=False
    )
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)
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
    speaking_benchmark_max_upload_mb: int = Field(default=100, ge=1, le=128)
    speaking_benchmark_max_duration_seconds: int = Field(default=1200, ge=1, le=1800)
    speaking_benchmark_execution: Literal["local", "remote", "disabled"] = "local"
    speaking_benchmark_grading_enabled: bool = False
    speaking_benchmark_grading_allow_live: bool = False
    speaking_benchmark_research_enabled: bool = False
    speaking_benchmark_questions_enabled: bool = False
    speaking_benchmark_questions_allow_live: bool = False
    speaking_benchmark_research_allow_live: bool = False
    speaking_benchmark_research_max_samples: int = Field(default=50, ge=1, le=100)
    speaking_benchmark_research_max_provider_seconds: int = Field(default=3600, ge=1, le=86400)
    speaking_benchmark_report_max_rows: int = Field(default=10000, ge=1, le=100000)
    speaking_benchmark_diarization_python: str = ""
    speaking_benchmark_model_dir: str = ""
    speaking_benchmark_threads: int = Field(default=2, ge=1, le=8)
    speaking_benchmark_memory_mb: int = Field(default=4096, ge=512, le=32768)
    speaking_benchmark_timeout_seconds: int = Field(default=3600, ge=5, le=7200)
    speaking_max_chunk_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    speaking_max_response_bytes: int = Field(default=32 * 1024 * 1024, ge=1024)
    speaking_recovery_window_seconds: int = Field(default=45, ge=10, le=120)
    speaking_normalizer_version: str = Field(default="pcm-v1", min_length=1, max_length=80)
    speaking_ffmpeg_path: str = "ffmpeg"
    speaking_processing_timeout_seconds: int = Field(default=120, ge=5, le=600)
    speaking_max_decoded_seconds: int = Field(default=600, ge=1, le=1800)
    speaking_asr_enabled: bool = False
    speaking_profile: Literal["legacy", "speaking_hybrid_v1"] = "legacy"
    speaking_azure_key: SecretStr | None = Field(default=None, repr=False)
    speaking_azure_region: str = Field(default="", max_length=80, pattern=r"^[a-z0-9-]*$")
    speaking_azure_allow_paid: bool = False
    speaking_azure_billing_mode: Literal["unknown", "free_only", "paid"] = "unknown"
    speaking_azure_locale: str = Field(default="en-US", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    speaking_azure_prosody: bool = True
    speaking_azure_timeout_seconds: int = Field(default=180, ge=5, le=600)
    speaking_azure_max_concurrency: int = Field(default=2, ge=1, le=16)
    speaking_azure_max_queue: int = Field(default=8, ge=0, le=100)
    speaking_azure_segmentation_silence_timeout_ms: int | None = Field(
        default=None, ge=100, le=5000
    )
    speaking_lexical_asr_provider: Literal[
        "azure_pa", "azure_stt", "faster_whisper_local", "faster_whisper_modal"
    ] = "azure_pa"
    speaking_lexical_asr_allow_additional_requests: bool = False
    speaking_lexical_asr_allow_gpu: bool = False
    speaking_lexical_asr_estimated_cost_usd_per_minute: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    speaking_lexical_asr_max_estimated_cost_usd_per_response: float | None = Field(
        default=None, gt=0, allow_inf_nan=False
    )
    speaking_vad_model_path: str = ""
    speaking_vad_model_sha256: str = (
        "597d30b3ec076608d059477bb14cfeffdf951bf5cae370d38f65d33bbfe82004"
    )
    speaking_asr_provider: Literal["local", "modal", "azure"] = "local"
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
    ai_writing_worker_enabled: bool = True
    ai_writing_worker_concurrency: int = Field(default=2, ge=1, le=32)
    ai_writing_max_running_runs: int = Field(default=4, ge=1, le=1000)
    ai_writing_max_pending_runs: int = Field(default=100, ge=1, le=100000)
    ai_writing_worker_poll_seconds: float = Field(default=2, gt=0, le=60, allow_inf_nan=False)
    ai_writing_lease_seconds: int = Field(default=60, ge=10, le=1800)
    ai_writing_provider: str = "vllm"
    ai_writing_vllm_base_url: str = ""
    ai_writing_vllm_api_key: str = Field(default="", repr=False)
    ai_writing_vllm_model: str = "mistralai/Ministral-3-8B-Instruct-2512"
    ai_writing_modal_key: str = Field(default="", repr=False)
    ai_writing_modal_secret: str = Field(default="", repr=False)
    ai_writing_openai_api_key: str = Field(default="", repr=False)
    ai_writing_openai_model: str = "gpt-6-luna"
    ai_writing_openai_base_url: str = "https://api.openai.com/v1"
    ai_writing_openai_profile: Literal["openai_task1_reasoned_v1"] = "openai_task1_reasoned_v1"
    ai_writing_openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = (
        "low"
    )
    ai_writing_openai_image_detail: Literal["auto", "low", "high", "original"] = "high"
    ai_writing_openai_low_completion_tokens: int = Field(default=8192, ge=128, le=32768)
    ai_writing_openai_medium_completion_tokens: int = Field(default=16384, ge=128, le=32768)
    ai_writing_openai_repair_completion_tokens: int = Field(default=32768, ge=128, le=32768)
    # Explicit safety cap. Incompatible profile budgets fail at OpenAI startup;
    # old 4096 configurations require an intentional budget migration.
    ai_writing_openai_max_output_tokens: int = Field(default=32768, ge=128, le=32768)
    ai_writing_openai_task1_image_assessment: bool = True
    ai_writing_openai_stage_timeout_seconds: float = Field(
        default=300, gt=0, le=900, allow_inf_nan=False
    )
    ai_writing_openai_run_timeout_seconds: float = Field(
        default=1800, gt=0, le=7200, allow_inf_nan=False
    )
    ai_writing_openai_stage_overrides: dict[str, OpenAIStageOverride] = Field(default_factory=dict)
    ai_writing_openai_max_concurrent_requests: int = Field(default=4, ge=1, le=32)
    ai_writing_openai_max_queued_requests: int = Field(default=16, ge=0, le=256)
    ai_writing_openai_readiness_retries: int = Field(default=2, ge=0, le=3)
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
    def select_speech_profile(self):
        # Explicit ASR selection activates the existing evidence contract, not another pipeline.
        # Missing credentials are validated at the ASR boundary so Writing can still start.
        if self.speaking_asr_provider == "azure":
            self.speaking_profile = "speaking_hybrid_v1"
        return self

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

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DevWebLocalforIELTS API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://ielts:ielts@localhost:5432/ielts"
    frontend_origin: str = "http://localhost:3000"
    storage_root: Path = Path("../storage")
    max_image_upload_mb: int = Field(default=10, gt=0)
    max_audio_upload_mb: int = Field(default=100, gt=0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("DATABASE_URL must point to PostgreSQL")
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

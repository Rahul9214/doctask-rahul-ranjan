from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings with secret-safe representations."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Project Assurance Register"
    app_version: str = "0.3.0"
    current_phase: str = "Phase 03 — Understand"
    implementation_status: str = (
        "Grounded Understand is implemented: classification, fact extraction, exact provenance "
        "validation, contradiction detection, and no-bluffing; Examine, human review, durable "
        "resume, MCP business operations, and watching are not implemented."
    )
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
    )
    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    source_storage_path: Path = Path("var/source-files")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    model_provider: Literal["deterministic", "openai"] = "deterministic"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    model_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    model_max_retries: int = Field(default=2, ge=0, le=5)

    def sqlalchemy_database_url(self) -> str:
        return self.database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache
from pathlib import Path

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
    app_version: str = "0.2.0"
    current_phase: str = "Phase 02 — Ingestion and Provenance"
    implementation_status: str = (
        "Deterministic corpus ingestion, exact provenance, and pgvector retrieval are implemented; "
        "agent reasoning is not implemented."
    )
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
    )
    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    source_storage_path: Path = Path("var/source-files")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)

    def sqlalchemy_database_url(self) -> str:
        return self.database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()

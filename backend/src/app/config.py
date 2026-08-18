from functools import lru_cache

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
    app_version: str = "0.1.0"
    current_phase: str = "Phase 01 — Development Foundation"
    implementation_status: str = "Task 1 business workflow is not implemented yet."
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
    )
    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)

    def sqlalchemy_database_url(self) -> str:
        return self.database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()

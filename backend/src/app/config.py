from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    app_version: str = "1.0.0"
    current_phase: str = "Phase 10 — Final Delivery"
    implementation_status: str = (
        "Phase 10 final delivery is implemented over the Phase 01–09 application: "
        "explicit approved-only register publication after completed human review, "
        "concurrent publication isolation, stage timing/usage/cost reporting, "
        "versioned ruleset configuration, and reproducible local Compose deployment. "
        "MCP remains a local-development stdio server over the same application "
        "services as HTTP. Generation never auto-approves or auto-publishes. "
        "MCP is trusted-client scope with corpus isolation and no production "
        "authentication. A Railway-hosted demonstration deployment is available; "
        "it is not an SLA-backed production service."
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
    watch_input_path: Path | None = None
    watch_poll_seconds: float = Field(default=2.0, gt=0, le=60)
    watch_stable_polls: int = Field(default=2, ge=2, le=10)
    ruleset_path: Path | None = None

    @field_validator("watch_input_path", "ruleset_path", mode="before")
    @classmethod
    def empty_optional_path(cls, value: object) -> object:
        if value == "":
            return None
        return value

    def sqlalchemy_database_url(self) -> str:
        return self.database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()

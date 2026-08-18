import pytest

from app.config import get_settings


def test_configuration_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "Configured Foundation")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://configured:configured-secret@db/configured",
    )
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "Configured Foundation"
    assert settings.sqlalchemy_database_url().endswith("@db/configured")
    assert "configured-secret" not in repr(settings)
    get_settings.cache_clear()

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.db import DependencyCheck, ReadinessReport
from app.main import create_app


def test_health_succeeds_without_calling_database_probe() -> None:
    async def forbidden_probe() -> ReadinessReport:
        raise AssertionError("The health endpoint must not check dependencies")

    with TestClient(create_app(readiness_probe=forbidden_probe)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready_reports_successful_dependencies() -> None:
    async def ready_probe() -> ReadinessReport:
        return ReadinessReport(
            status="ready",
            checks={
                "database": DependencyCheck(status="ready"),
                "pgvector": DependencyCheck(status="ready", version="0.8.1"),
            },
        )

    with TestClient(create_app(readiness_probe=ready_probe)) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "database": {"status": "ready", "version": None, "detail": None, "action": None},
            "pgvector": {
                "status": "ready",
                "version": "0.8.1",
                "detail": None,
                "action": None,
            },
        },
    }


def test_ready_returns_actionable_safe_failure_when_database_is_unavailable() -> None:
    secret = "must-not-appear"
    settings = Settings(
        database_url=SecretStr(f"postgresql+asyncpg://foundation:{secret}@127.0.0.1:1/unreachable"),
        readiness_timeout_seconds=0.5,
    )

    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/ready")

    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "unavailable"
    assert body["checks"]["database"]["status"] == "unavailable"
    assert body["checks"]["database"]["action"]
    assert secret not in response.text


def test_version_is_truthful_about_phase_scope() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "app_version": "0.1.0",
        "current_phase": "Phase 01 — Development Foundation",
        "implementation_status": "Task 1 business workflow is not implemented yet.",
    }

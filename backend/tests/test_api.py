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
    database_url = f"postgresql+asyncpg://foundation:{secret}@127.0.0.1:1/unreachable"
    settings = Settings(
        database_url=SecretStr(database_url),
        readiness_timeout_seconds=0.5,
    )

    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/ready")

    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "unavailable"
    assert body["checks"]["database"]["status"] == "unavailable"
    assert body["checks"]["database"]["detail"]
    assert body["checks"]["database"]["action"]
    assert secret not in response.text
    assert database_url not in response.text
    assert "ConnectionRefusedError" not in response.text
    assert "Connect call failed" not in response.text


def test_version_is_truthful_about_phase_scope() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "app_version": "0.8.0",
        "current_phase": "Phase 08 — MCP Operations",
        "implementation_status": (
            "MCP business operations are implemented as a stdio server over the same application "
            "services as HTTP: corpus/source inspection, durable workflow start/inspect/resume, "
            "understanding and examination inspection, explicit item-level review "
            "(approve/reject/edit/complete), and incremental evidence inspection. Generation never "
            "auto-approves. MCP is local-development / trusted-client scope with corpus isolation "
            "and no production authentication. Register publication is not implemented."
        ),
    }

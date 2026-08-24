import logging
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.db import DependencyCheck, ReadinessReport
from app.errors import NotFoundError
from app.main import create_app

TESTS_DIR = Path(__file__).resolve().parent


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
        "app_version": "1.0.0",
        "current_phase": "Phase 10 — Final Delivery",
        "implementation_status": (
            "Phase 10 final delivery is implemented over the Phase 01–09 application: "
            "explicit approved-only register publication after completed human review, "
            "concurrent publication isolation, stage timing/usage/cost reporting, "
            "versioned ruleset configuration, and reproducible local Compose deployment. "
            "MCP remains a local-development stdio server over the same application "
            "services as HTTP. Generation never auto-approves or auto-publishes. "
            "MCP is trusted-client scope with corpus isolation and no production "
            "authentication. A Railway-hosted demonstration deployment is available; "
            "it is not an SLA-backed production service."
        ),
    }


def test_unexpected_http_error_is_sanitized_in_response_and_server_logs(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    application = create_app()
    sentinels = (
        "SECRET_SENTINEL_DO_NOT_LEAK",
        "SOURCE_TEXT_SENTINEL_DO_NOT_LEAK",
        "postgresql://credential-sentinel",
    )
    raw_message = " | ".join(sentinels)

    @application.get("/test/unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError(raw_message)

    with caplog.at_level(logging.ERROR, logger="app.http"), TestClient(application) as client:
        response = client.get("/test/unexpected-error")
    captured = capsys.readouterr()
    observable_output = "\n".join((response.text, caplog.text, captured.out, captured.err))

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "detail": "The operation could not be completed safely.",
        "action": "Retry the request or inspect service health.",
    }
    assert "Unhandled HTTP request failure" in caplog.text
    for sentinel in sentinels:
        assert sentinel not in observable_output
    assert raw_message not in observable_output
    assert "traceback" not in observable_output.casefold()
    assert "runtimeerror" not in observable_output.casefold()


def test_known_application_error_preserves_specific_contract() -> None:
    application = create_app()

    @application.get("/test/known-error")
    async def known_error() -> None:
        raise NotFoundError(
            "known_resource_missing",
            "The requested test resource was not found.",
            "Use a known test resource identifier.",
        )

    with TestClient(application) as client:
        response = client.get("/test/known-error")

    assert response.status_code == 404
    assert response.json() == {
        "code": "known_resource_missing",
        "detail": "The requested test resource was not found.",
        "action": "Use a known test resource identifier.",
    }


def test_uvicorn_stderr_does_not_receive_unexpected_exception_text() -> None:
    sentinels = (
        "SECRET_SENTINEL_DO_NOT_LEAK",
        "SOURCE_TEXT_SENTINEL_DO_NOT_LEAK",
        "postgresql://credential-sentinel",
    )
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "uvicorn_error_app:app",
            "--app-dir",
            str(TESTS_DIR),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "debug",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    response_status: int | None = None
    response_body = ""
    stdout = ""
    stderr = ""
    try:
        health_url = f"http://127.0.0.1:{port}/health"
        ready = False
        for _attempt in range(100):
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(health_url, timeout=0.2) as health:
                    if health.status == 200:
                        ready = True
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(0.05)
        if not ready:
            pytest.fail("Uvicorn did not become ready for the log-boundary probe.")

        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/unexpected",
                timeout=2,
            )
        except urllib.error.HTTPError as error:
            response_status = error.code
            response_body = error.read().decode("utf-8")
        time.sleep(0.1)
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)

    observable_output = "\n".join((response_body, stdout, stderr))
    assert response_status == 500
    assert '"code":"internal_error"' in response_body
    assert "Unhandled HTTP request failure" in observable_output
    for sentinel in sentinels:
        assert sentinel not in observable_output
    assert "traceback" not in observable_output.casefold()
    assert "runtimeerror" not in observable_output.casefold()

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"

FORBIDDEN_PACKAGES = {
    "redis",
    "celery",
    "kafka",
    "kafka-python",
    "confluent-kafka",
    "kubernetes",
    "boto3",
}


def test_lockfiles_are_committed_and_runtime_stays_small() -> None:
    assert (BACKEND_ROOT / "uv.lock").exists()
    assert (FRONTEND_ROOT / "package-lock.json").exists()
    pyproject = (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for package in FORBIDDEN_PACKAGES:
        assert f'"{package}' not in pyproject
        assert f" {package}" not in pyproject.split("[project]")[1].split("[dependency-groups]")[0]
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen" in dockerfile
    frontend_docker = (FRONTEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "npm ci" in frontend_docker
    assert "npm install" not in frontend_docker


def test_network_vulnerability_audit_is_not_fabricated() -> None:
    """pip-audit / npm audit are not a Phase 09 gate; absence is recorded, not PASS."""

    assert not (BACKEND_ROOT / "pip-audit-report.json").exists()

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]

EXACT_ALLOWED_TOKENS = frozenset(
    {
        "sk-test-secret-should-not-leak",
        "SECRET_SENTINEL_DO_NOT_LEAK",
        "SOURCE_TEXT_SENTINEL_DO_NOT_LEAK",
        "postgresql://credential-sentinel",
    }
)

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".docx",
    ".woff",
    ".woff2",
    ".ico",
    ".lock",
}
SKIP_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "htmlcov",
}

SECRET_PATTERNS = (
    ("openai_key", re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(r"(?:ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----")),
    (
        "remote_dsn",
        re.compile(
            r"postgres(?:ql)?(?:\+\w+)?://[^/\s:]+:[^/\s@]+@(?!localhost\b|127\.0\.0\.1\b|db\b)"
        ),
    ),
)


def _git_files(*extra: str) -> list[str] | None:
    result = subprocess.run(
        ["git", *extra],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _candidate_files() -> tuple[list[Path], str]:
    tracked = _git_files("ls-files")
    untracked = _git_files("ls-files", "--others", "--exclude-standard")
    if tracked is not None and untracked is not None:
        relatives = sorted(set(tracked) | set(untracked))
        return [REPO_ROOT / item for item in relatives], "git-tracked-and-untracked"
    files: list[Path] = []
    for root in (
        REPO_ROOT / "backend" / "src",
        REPO_ROOT / "backend" / "tests",
        REPO_ROOT / "frontend" / "src",
    ):
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return files, "filesystem-fallback-without-git"


def _should_skip(path: Path) -> bool:
    if any(part in SKIP_DIR_PARTS for part in path.parts):
        return True
    return path.suffix.casefold() in SKIP_SUFFIXES


def test_source_candidates_have_no_real_secrets_and_env_is_untracked() -> None:
    files, source = _candidate_files()
    tracked = _git_files("ls-files") or []
    assert ".env" not in tracked
    assert ".env.local" not in tracked
    assert ".env.production" not in tracked

    findings: list[str] = []
    for path in files:
        if not path.exists() or not path.is_file() or _should_skip(path):
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if path.name == ".env" or path.suffix.casefold() == ".pem":
            findings.append(f"{relative}: committed environment/private key file")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(0)
                if value in EXACT_ALLOWED_TOKENS:
                    continue
                findings.append(f"{relative}: {label} {value[:24]}")
    assert findings == [], f"unexpected secret-like material ({source}):\n" + "\n".join(findings)

    example = REPO_ROOT / ".env.example"
    assert example.exists()
    example_text = example.read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD=local_only" in example_text
    assert "OPENAI_API_KEY=sk-" not in example_text
    assert re.search(r"^OPENAI_API_KEY=", example_text, re.MULTILINE) is None
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0


def test_fake_test_sentinels_are_exact_named_constants() -> None:
    text = (BACKEND_ROOT / "src" / "app" / "mcp_errors.py").read_text(encoding="utf-8")
    assert 'TEST_SENTINEL_SECRET = "SECRET_SENTINEL_DO_NOT_LEAK"' in text
    assert 'TEST_SENTINEL_SOURCE = "SOURCE_TEXT_SENTINEL_DO_NOT_LEAK"' in text
    assert 'TEST_SENTINEL_DSN = "postgresql://credential-sentinel"' in text
    assert "sk-test-secret-should-not-leak" in (
        BACKEND_ROOT / "tests" / "test_model_boundary.py"
    ).read_text(encoding="utf-8")

"""Regenerate docs/measurements/phase-09-local.json from the executable measurement test."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    env["WRITE_PHASE09_MEASUREMENTS"] = "1"
    if not env.get("TEST_DATABASE_URL"):
        print("TEST_DATABASE_URL must be set to run the measurement writer.", file=sys.stderr)
        return 2
    env.setdefault("ALLOW_DESTRUCTIVE_TEST_DATABASE", "true")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_phase09_measurements.py",
        "-v",
        "--no-cov",
    ]
    completed = subprocess.run(command, cwd=BACKEND_ROOT, env=env, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

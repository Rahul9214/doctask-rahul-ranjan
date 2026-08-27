"""Idempotent Aurora/Harbor demo corpus bootstrap.

Creates missing canonical demo corpora, ingests fixture documents without
duplicating existing source versions, creates the initial current durable
revision when it is missing, and skips already-correct corpora.

    uv run python scripts/bootstrap_demo_corpora.py
    python -m app.demo_bootstrap
"""

from __future__ import annotations

from app.demo_bootstrap import main

if __name__ == "__main__":
    main()

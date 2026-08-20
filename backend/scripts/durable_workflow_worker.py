"""Subprocess entry for Phase 06 real process-kill / resume proof.

Start a run until a checkpointed stage barrier, then resume the same run in a
new process:

    uv run python scripts/durable_workflow_worker.py start --corpus-id UUID \\
        --storage-path PATH --hold-after understand --barrier-path PATH

    uv run python scripts/durable_workflow_worker.py resume --corpus-id UUID \\
        --run-id UUID --storage-path PATH
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from pydantic import SecretStr

from app.checkpointer import configure_windows_psycopg_loop
from app.config import Settings
from app.db import create_engine, create_session_factory
from app.examine_service import ExamineService
from app.model_gateway import DeterministicModelAdapter
from app.review_service import ReviewService
from app.services import Phase02Service
from app.storage import LocalFileStorage
from app.understand_service import UnderstandService
from app.workflow_barriers import BARRIER_PATH_ENV, HOLD_AFTER_ENV
from app.workflow_service import WorkflowService


def _service(storage_path: Path) -> WorkflowService:
    database_url = os.environ["DATABASE_URL"]
    settings = Settings(database_url=SecretStr(database_url))
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    phase02 = Phase02Service(
        session_factory,
        LocalFileStorage(storage_path, settings.max_upload_bytes),
    )
    adapter = DeterministicModelAdapter()
    understand = UnderstandService(session_factory, phase02, adapter, settings)
    examine = ExamineService(session_factory, phase02, understand)
    review = ReviewService(session_factory, phase02, examine)
    return WorkflowService(
        session_factory,
        phase02,
        examine,
        review,
        adapter,
        settings,
        database_url=database_url,
    )


async def _start(corpus_id: UUID, storage_path: Path) -> None:
    workflow = _service(storage_path)
    run = await workflow.create_run(corpus_id)
    print(json.dumps({"ok": True, "run_id": str(run.id), "status": run.status}), flush=True)


async def _resume(corpus_id: UUID, run_id: UUID, storage_path: Path) -> None:
    os.environ.pop(HOLD_AFTER_ENV, None)
    os.environ.pop(BARRIER_PATH_ENV, None)
    workflow = _service(storage_path)
    run = await workflow.resume_run(corpus_id, run_id)
    print(
        json.dumps(
            {
                "ok": True,
                "run_id": str(run.id),
                "status": run.status,
                "current_stage": run.current_stage,
                "resume_count": run.resume_count,
                "analysis_run_id": str(run.analysis_run_id) if run.analysis_run_id else None,
            }
        ),
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Durable workflow subprocess worker")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--corpus-id", required=True)
    start.add_argument("--storage-path", required=True)
    start.add_argument("--hold-after", default="")
    start.add_argument("--barrier-path", default="")
    resume = sub.add_parser("resume")
    resume.add_argument("--corpus-id", required=True)
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--storage-path", required=True)
    args = parser.parse_args(argv)
    if args.command == "start":
        if args.hold_after:
            os.environ[HOLD_AFTER_ENV] = args.hold_after
        if args.barrier_path:
            os.environ[BARRIER_PATH_ENV] = args.barrier_path
        configure_windows_psycopg_loop()
        asyncio.run(_start(UUID(args.corpus_id), Path(args.storage_path)))
        return 0
    configure_windows_psycopg_loop()
    asyncio.run(_resume(UUID(args.corpus_id), UUID(args.run_id), Path(args.storage_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

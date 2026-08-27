"""Real process-kill / resume proof across a process boundary."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import ingest_workflow_corpus
from sqlalchemy import select, text

from app.models import DurableOperation, ReviewDecision, WorkflowRun, WorkflowRunEvent
from app.services import Phase02Service
from app.storage import LocalFileStorage

BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKER = BACKEND_ROOT / "scripts" / "durable_workflow_worker.py"
BARRIER_TIMEOUT_SECONDS = 90
RESUME_TIMEOUT_SECONDS = 120


@pytest.mark.integration
async def test_real_process_kill_then_new_process_resumes_same_run(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, storage = phase02_service
    corpus = await ingest_workflow_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    barrier_path = tmp_path / "understand-barrier.json"
    env = os.environ.copy()
    env["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    env["MODEL_PROVIDER"] = "deterministic"
    started = await asyncio.to_thread(
        _start_worker,
        [
            sys.executable,
            str(WORKER),
            "start",
            "--corpus-id",
            str(corpus.id),
            "--storage-path",
            str(storage.root),
            "--hold-after",
            "understand",
            "--barrier-path",
            str(barrier_path),
        ],
        env,
    )
    try:
        await _wait_for_file(barrier_path, BARRIER_TIMEOUT_SECONDS, started)
        payload = json.loads(await asyncio.to_thread(_read_text, barrier_path))
        run_id = payload["workflow_run_id"]
        assert payload["stage"] == "understand"
        async with phase02.session_factory() as session:
            run = await session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.id == run_id,
                    WorkflowRun.corpus_id == corpus.id,
                )
            )
            checkpoint = await session.execute(
                text("SELECT checkpoint_id FROM checkpoints WHERE thread_id = :thread_id LIMIT 1"),
                {"thread_id": str(run_id)},
            )
            operations = list(
                await session.scalars(
                    select(DurableOperation).where(DurableOperation.workflow_run_id == run_id)
                )
            )
        assert run is not None
        assert run.analysis_run_id is not None
        assert checkpoint.first() is not None
        logical_before = sum(item.logical_operation_count for item in operations)
        assert logical_before >= 1
        started.kill()
        await asyncio.to_thread(started.wait, 15)
        assert started.returncode is not None
    finally:
        if started.poll() is None:
            started.kill()
            await asyncio.to_thread(started.wait, 15)

    resumed = await asyncio.to_thread(
        _run_worker,
        [
            sys.executable,
            str(WORKER),
            "resume",
            "--corpus-id",
            str(corpus.id),
            "--run-id",
            str(run_id),
            "--storage-path",
            str(storage.root),
        ],
        env,
    )
    assert resumed.returncode == 0, resumed.stderr
    result = json.loads(resumed.stdout.strip().splitlines()[-1])
    assert result["run_id"] == str(run_id)
    assert result["status"] == "waiting_for_review"
    assert result["resume_count"] >= 1
    async with phase02.session_factory() as session:
        run = await session.scalar(
            select(WorkflowRun).where(
                WorkflowRun.id == run_id,
                WorkflowRun.corpus_id == corpus.id,
            )
        )
        operations = list(
            await session.scalars(
                select(DurableOperation).where(DurableOperation.workflow_run_id == run_id)
            )
        )
        events = list(
            await session.scalars(
                select(WorkflowRunEvent).where(WorkflowRunEvent.workflow_run_id == run_id)
            )
        )
        decisions = list(
            await session.scalars(
                select(ReviewDecision).where(ReviewDecision.corpus_id == corpus.id)
            )
        )
    assert run is not None
    assert run.status == "waiting_for_review"
    assert run.analysis_run_id is not None
    assert sum(item.logical_operation_count for item in operations) == logical_before
    understand_completed = [
        event
        for event in events
        if event.event_type == "stage_completed" and event.stage_name == "understand"
    ]
    assert len(understand_completed) == 1
    assert decisions == []


async def _wait_for_file(
    path: Path,
    timeout_seconds: float,
    process: subprocess.Popen[str],
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        code = process.poll()
        if code is not None:
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise AssertionError(
                f"worker exited before the barrier file was written: code={code} stderr={stderr}"
            )
        if await asyncio.to_thread(_barrier_ready, path):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"barrier file was not written: {path}")


def _start_worker(args: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        args,
        cwd=str(BACKEND_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _run_worker(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(BACKEND_ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=RESUME_TIMEOUT_SECONDS,
    )


def _barrier_ready(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

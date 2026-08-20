"""Test hooks that pause a durable workflow after a checkpointed stage."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

HOLD_AFTER_ENV = "WORKFLOW_HOLD_AFTER_STAGE"
BARRIER_PATH_ENV = "WORKFLOW_BARRIER_PATH"
RELEASE_PATH_ENV = "WORKFLOW_RELEASE_PATH"


async def hold_after_checkpoint(*, stage: str, workflow_run_id: UUID, corpus_id: UUID) -> None:
    """Pause only when a test asks this process to hold after a named stage.

    The barrier file is written after the previous LangGraph node has been
    checkpointed. Resume processes leave the hold environment unset.
    """

    if os.environ.get(HOLD_AFTER_ENV) != stage:
        return
    barrier_path = os.environ.get(BARRIER_PATH_ENV)
    if barrier_path:
        path = Path(barrier_path)
        payload = json.dumps(
            {
                "stage": stage,
                "workflow_run_id": str(workflow_run_id),
                "corpus_id": str(corpus_id),
            }
        )
        await asyncio.to_thread(_write_barrier, path, payload)
    release_path = os.environ.get(RELEASE_PATH_ENV)
    while True:
        if release_path is not None and await asyncio.to_thread(_path_exists, release_path):
            return
        await asyncio.sleep(0.05)


def _write_barrier(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _path_exists(path: str) -> bool:
    return Path(path).exists()

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pytest
from helpers import CountingModelAdapter, ingest_corpus, make_workflow
from sqlalchemy import func, select

from app.errors import ModelError
from app.model_gateway import BlockContext, ClassificationBatch, ExtractionBatch
from app.models import DurableOperation, WorkflowRun
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_concurrent_resume_of_same_run_is_serialized(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    adapter = _ExclusiveSlowAdapter()
    first_service = make_workflow(phase02, adapter=adapter)
    second_service = make_workflow(phase02, adapter=adapter)
    pending = await first_service._create_pending_run(corpus.id)
    left, right = await asyncio.gather(
        first_service.resume_run(corpus.id, pending.id),
        second_service.resume_run(corpus.id, pending.id),
    )
    assert left.id == right.id == pending.id
    assert left.status == right.status == "waiting_for_review"
    assert adapter.max_active == 1
    assert adapter.calls == 1
    latest = await first_service.get_run(corpus.id, pending.id)
    assert latest.resume_count == 2
    events = await first_service.list_events(corpus.id, pending.id)
    started = [event for event in events if event.event_type == "workflow_started"]
    resumed = [event for event in events if event.event_type == "workflow_resumed"]
    understand_completed = [
        event
        for event in events
        if event.event_type == "stage_completed" and event.stage_name == "understand"
    ]
    assert len(started) == 0
    assert len(resumed) == 2
    assert len(understand_completed) == 1
    async with phase02.session_factory() as session:
        operations = list(
            await session.scalars(
                select(DurableOperation).where(DurableOperation.workflow_run_id == pending.id)
            )
        )
        run_count = await session.scalar(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.id == pending.id)
        )
    assert run_count == 1
    assert all(item.logical_operation_count == 1 for item in operations)
    assert sum(item.logical_operation_count for item in operations) == 2


@pytest.mark.integration
async def test_concurrent_failed_resume_resets_checkpoint_once(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    adapter = _ExclusiveFailThenSucceedAdapter()
    first_service = make_workflow(phase02, adapter=adapter)
    second_service = make_workflow(phase02, adapter=adapter)
    failed = await first_service.create_run(corpus.id)
    assert failed.status == "failed"
    left, right = await asyncio.gather(
        first_service.resume_run(corpus.id, failed.id),
        second_service.resume_run(corpus.id, failed.id),
    )
    assert {left.status, right.status} == {"waiting_for_review"}
    assert adapter.max_active == 1
    assert adapter.calls == 2
    events = await first_service.list_events(corpus.id, failed.id)
    resets = [event for event in events if event.event_type == "checkpoint_reset_for_failed_resume"]
    understand_completed = [
        event
        for event in events
        if event.event_type == "stage_completed" and event.stage_name == "understand"
    ]
    failed_events = [event for event in events if event.event_type == "stage_failed"]
    assert len(resets) == 1
    assert len(understand_completed) == 1
    assert len(failed_events) == 1
    latest = await first_service.get_run(corpus.id, failed.id)
    assert latest.resume_count == 2
    async with phase02.session_factory() as session:
        operations = list(
            await session.scalars(
                select(DurableOperation).where(DurableOperation.workflow_run_id == failed.id)
            )
        )
        run_count = await session.scalar(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.id == failed.id)
        )
    assert run_count == 1
    assert sum(item.logical_operation_count for item in operations) == 2


@pytest.mark.integration
async def test_concurrent_resume_of_waiting_run_does_not_bypass_review(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    first_service = make_workflow(phase02)
    second_service = make_workflow(phase02)
    run = await first_service.create_run(corpus.id)
    assert run.status == "waiting_for_review"
    left, right = await asyncio.gather(
        first_service.resume_run(corpus.id, run.id),
        second_service.resume_run(corpus.id, run.id),
    )
    assert left.id == right.id == run.id
    assert left.status == right.status == "waiting_for_review"
    latest = await first_service.get_run(corpus.id, run.id)
    assert latest.status == "waiting_for_review"
    assert latest.resume_count == 2
    events = await first_service.list_events(corpus.id, run.id)
    completed = [event for event in events if event.event_type == "workflow_completed"]
    understand_completed = [
        event
        for event in events
        if event.event_type == "stage_completed" and event.stage_name == "understand"
    ]
    started = [event for event in events if event.event_type == "workflow_started"]
    resumed = [event for event in events if event.event_type == "workflow_resumed"]
    assert completed == []
    assert len(understand_completed) == 1
    assert len(started) == 1
    assert len(resumed) == 2
    assert run.review_session_id is not None
    session = await first_service.review.get_session(corpus.id, run.review_session_id)
    assert session.status != "completed"
    assert session.pending_count > 0
    assert session.approved_count == 0


class _ExclusiveSlowAdapter:
    mode: Literal["deterministic", "openai"] = "deterministic"
    model_name = "deterministic-local"

    def __init__(self) -> None:
        self.inner = CountingModelAdapter()
        self.calls = 0
        self.active = 0
        self.max_active = 0

    async def classify_blocks(self, blocks: Sequence[BlockContext]) -> ClassificationBatch:
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.15)
            return await self.inner.classify_blocks(blocks)
        finally:
            self.active -= 1

    async def extract_facts(self, blocks: Sequence[BlockContext]) -> ExtractionBatch:
        return await self.inner.extract_facts(blocks)


class _ExclusiveFailThenSucceedAdapter:
    mode: Literal["deterministic", "openai"] = "deterministic"
    model_name = "deterministic-local"

    def __init__(self) -> None:
        self.inner = CountingModelAdapter()
        self.calls = 0
        self.active = 0
        self.max_active = 0

    async def classify_blocks(self, blocks: Sequence[BlockContext]) -> ClassificationBatch:
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.15)
            if self.calls == 1:
                raise ModelError(
                    "model_unavailable",
                    "The model provider could not be reached.",
                    "Retry the workflow run.",
                    retryable=True,
                    attempt_count=1,
                )
            return await self.inner.classify_blocks(blocks)
        finally:
            self.active -= 1

    async def extract_facts(self, blocks: Sequence[BlockContext]) -> ExtractionBatch:
        return await self.inner.extract_facts(blocks)

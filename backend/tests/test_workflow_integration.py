import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from helpers import (
    CountingModelAdapter,
    complete_required_review,
    ingest_corpus,
    ledger_identity,
    make_workflow,
)
from sqlalchemy import select, text

from app.errors import ModelError, NotFoundError, ValidationError
from app.model_gateway import BlockContext, ClassificationBatch, ExtractionBatch
from app.models import DurableOperation, ExaminationRun, ReviewDecision, WorkflowRun
from app.operation_ledger import OperationLedger, canonical_json, make_operation_key, sha256_hex
from app.services import Phase02Service
from app.storage import LocalFileStorage
from app.workflow_service import WorkflowService


@pytest.mark.integration
async def test_workflow_run_persists_and_waits_at_human_gate(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    run = await workflow.create_run(corpus.id)
    events = await workflow.list_events(corpus.id, run.id)
    assert run.status == "waiting_for_review"
    assert run.current_stage == "wait_for_review"
    assert run.analysis_run_id is not None
    assert run.examination_run_id is not None
    assert run.review_session_id is not None
    assert run.checkpoint_thread_id == str(run.id)
    assert run.resume_count == 0
    assert {event.event_type for event in events} >= {
        "workflow_created",
        "workflow_started",
        "stage_completed",
        "waiting_for_review",
        "checkpoint_recorded",
    }
    async with phase02.session_factory() as session:
        checkpoint = await session.execute(
            text("SELECT thread_id FROM checkpoints WHERE thread_id = :thread_id LIMIT 1"),
            {"thread_id": run.checkpoint_thread_id},
        )
        operations = list(
            await session.scalars(
                select(DurableOperation).where(DurableOperation.workflow_run_id == run.id)
            )
        )
        decisions = list(
            await session.scalars(
                select(ReviewDecision).where(ReviewDecision.corpus_id == corpus.id)
            )
        )
    assert checkpoint.first() is not None
    assert {item.operation_type for item in operations} == {"classify", "extract"}
    assert all(item.logical_operation_count == 1 for item in operations)
    assert all(item.status == "completed" for item in operations)
    assert decisions == []

    resumed = await workflow.resume_run(corpus.id, run.id)
    assert resumed.status == "waiting_for_review"
    assert resumed.resume_count == 1
    later_events = await workflow.list_events(corpus.id, run.id)
    assert any(event.event_type == "workflow_resumed" for event in later_events)
    async with phase02.session_factory() as session:
        decisions = list(
            await session.scalars(
                select(ReviewDecision).where(ReviewDecision.corpus_id == corpus.id)
            )
        )
        operations_after = list(
            await session.scalars(
                select(DurableOperation).where(DurableOperation.workflow_run_id == run.id)
            )
        )
    assert decisions == []
    assert sum(item.logical_operation_count for item in operations_after) == 2

    assert run.review_session_id is not None
    await complete_required_review(workflow.review, corpus.id, run.review_session_id)
    finished = await workflow.resume_run(corpus.id, run.id)
    assert finished.status == "completed"
    assert finished.current_stage == "completed"
    with pytest.raises(ValidationError) as error:
        await workflow.resume_run(corpus.id, run.id)
    assert error.value.code == "workflow_run_already_completed"


@pytest.mark.integration
async def test_workflow_corpus_isolation_and_same_corpus_concurrency(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    workflow = make_workflow(phase02)
    first, second = await _gather_runs(workflow, aurora.id)
    assert first.id != second.id
    assert first.checkpoint_thread_id != second.checkpoint_thread_id
    assert first.analysis_run_id != second.analysis_run_id
    assert first.review_session_id != second.review_session_id
    async with phase02.session_factory() as session:
        keys = list(
            await session.scalars(
                select(DurableOperation.operation_key).where(
                    DurableOperation.corpus_id == aurora.id
                )
            )
        )
        checkpoints = await session.execute(
            text("SELECT thread_id FROM checkpoints WHERE thread_id IN (:a, :b)"),
            {"a": first.checkpoint_thread_id, "b": second.checkpoint_thread_id},
        )
    assert len(keys) == len(set(keys))
    threads = {row[0] for row in checkpoints.fetchall()}
    assert first.checkpoint_thread_id in threads
    assert second.checkpoint_thread_id in threads

    with pytest.raises(NotFoundError) as missing:
        await workflow.get_run(harbor.id, first.id)
    assert missing.value.code == "workflow_run_not_found"


@pytest.mark.integration
async def test_idempotent_ledger_reuse_retry_and_ambiguous_window(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    adapter = CountingModelAdapter(fail_classify_attempts=2)
    workflow = make_workflow(phase02, adapter=adapter)
    run = await workflow.create_run(corpus.id)
    assert adapter.classify_operations == 1
    assert adapter.classify_attempts == 3
    assert adapter.extract_operations == 1
    async with phase02.session_factory() as session:
        classify = await session.scalar(
            select(DurableOperation).where(
                DurableOperation.workflow_run_id == run.id,
                DurableOperation.operation_type == "classify",
            )
        )
    assert classify is not None
    assert classify.logical_operation_count == 1
    assert classify.provider_attempt_count == 3
    assert adapter.classify_operations == 1

    ledger = OperationLedger(phase02.session_factory)
    request = {"probe": "ambiguous"}
    request_hash = sha256_hex(canonical_json(request))
    key = make_operation_key(
        workflow_run_id=run.id,
        stage="understand",
        operation_type="probe",
        source_input_version=str(run.configuration["source_input_version"]),
        request_hash=request_hash,
        model_provider="deterministic",
        model_name="deterministic-local",
        **ledger_identity(run),
    )
    async with phase02.session_factory() as session, session.begin():
        session.add(
            DurableOperation(
                corpus_id=corpus.id,
                workflow_run_id=run.id,
                operation_key=key,
                operation_type="probe",
                stage="understand",
                status="in_flight",
                request_hash=request_hash,
                result_payload={},
                logical_operation_count=0,
                provider_attempt_count=1,
                source_input_version=str(run.configuration["source_input_version"]),
                model_provider="deterministic",
                model_name="deterministic-local",
            )
        )
    with pytest.raises(ModelError) as error:
        await ledger.execute(
            corpus_id=corpus.id,
            workflow_run_id=run.id,
            stage="understand",
            operation_type="probe",
            source_input_version=str(run.configuration["source_input_version"]),
            request=request,
            model_provider="deterministic",
            model_name="deterministic-local",
            **ledger_identity(run),
            fn=_should_not_run,
            dump=lambda value: value,
            restore=lambda payload: payload,
            reconcile_ambiguous=False,
        )
    assert error.value.code == "operation_ambiguous"
    recovered = await ledger.execute(
        corpus_id=corpus.id,
        workflow_run_id=run.id,
        stage="understand",
        operation_type="probe",
        source_input_version=str(run.configuration["source_input_version"]),
        request=request,
        model_provider="deterministic",
        model_name="deterministic-local",
        **ledger_identity(run),
        fn=_probe_result,
        dump=lambda value: value,
        restore=lambda payload: payload,
        reconcile_ambiguous=True,
    )
    assert recovered == {"ok": True}
    reused = await ledger.execute(
        corpus_id=corpus.id,
        workflow_run_id=run.id,
        stage="understand",
        operation_type="probe",
        source_input_version=str(run.configuration["source_input_version"]),
        request=request,
        model_provider="deterministic",
        model_name="deterministic-local",
        **ledger_identity(run),
        fn=_should_not_run,
        dump=lambda value: value,
        restore=lambda payload: payload,
        reconcile_ambiguous=False,
    )
    assert reused == {"ok": True}
    concurrent_request = {"probe": "concurrent"}

    async def _once() -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {"ok": True}

    first, second = await asyncio.gather(
        ledger.execute(
            corpus_id=corpus.id,
            workflow_run_id=run.id,
            stage="understand",
            operation_type="concurrent-probe",
            source_input_version=str(run.configuration["source_input_version"]),
            request=concurrent_request,
            model_provider="deterministic",
            model_name="deterministic-local",
            **ledger_identity(run),
            fn=_once,
            dump=lambda value: value,
            restore=lambda payload: payload,
            reconcile_ambiguous=True,
        ),
        ledger.execute(
            corpus_id=corpus.id,
            workflow_run_id=run.id,
            stage="understand",
            operation_type="concurrent-probe",
            source_input_version=str(run.configuration["source_input_version"]),
            request=concurrent_request,
            model_provider="deterministic",
            model_name="deterministic-local",
            **ledger_identity(run),
            fn=_once,
            dump=lambda value: value,
            restore=lambda payload: payload,
            reconcile_ambiguous=True,
        ),
    )
    assert first == second
    async with phase02.session_factory() as session:
        concurrent_ops = list(
            await session.scalars(
                select(DurableOperation).where(
                    DurableOperation.workflow_run_id == run.id,
                    DurableOperation.operation_type == "concurrent-probe",
                )
            )
        )
    assert len(concurrent_ops) == 1
    assert concurrent_ops[0].logical_operation_count == 1


@pytest.mark.integration
async def test_model_failure_is_durable_and_resumable(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    adapter = _FailThenSucceedAdapter()
    workflow = make_workflow(phase02, adapter=adapter)
    failed = await workflow.create_run(corpus.id)
    assert failed.status == "failed"
    assert failed.error_code == "model_unavailable"
    assert failed.error_action
    assert "traceback" not in (failed.error_detail or "").casefold()
    recovered = await workflow.resume_run(corpus.id, failed.id)
    assert recovered.status == "waiting_for_review", (
        recovered.status,
        recovered.current_stage,
        recovered.error_code,
        recovered.error_detail,
        adapter.calls,
    )
    assert recovered.resume_count == 1
    events = await workflow.list_events(corpus.id, failed.id)
    assert any(event.event_type == "stage_failed" for event in events)
    assert any(event.event_type == "stage_completed" for event in events)


@pytest.mark.integration
async def test_failed_examine_stage_is_not_recorded_as_completed(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    create_examination = workflow.examine.create_run

    async def create_failed_examination(corpus_id: UUID, analysis_run_id: UUID) -> ExaminationRun:
        examination = await create_examination(corpus_id, analysis_run_id)
        examination.status = "failed"
        examination.error_code = "examine_probe_failed"
        examination.error_detail = "Synthetic Examine failure."
        return examination

    monkeypatch.setattr(workflow.examine, "create_run", create_failed_examination)

    failed = await workflow.create_run(corpus.id)
    events = await workflow.list_events(corpus.id, failed.id)
    examine_events = [event for event in events if event.stage_name == "examine"]

    assert failed.status == "failed"
    assert failed.error_code == "examine_probe_failed"
    assert any(event.event_type == "stage_failed" for event in examine_events)
    assert all(event.event_type != "stage_completed" for event in examine_events)


@pytest.mark.integration
async def test_resume_without_checkpoint_reinitializes_same_run(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    pending = await workflow._create_pending_run(corpus.id)
    async with phase02.session_factory() as session:
        runs = list(
            await session.scalars(select(WorkflowRun).where(WorkflowRun.corpus_id == corpus.id))
        )
        checkpoint = await session.execute(
            text("SELECT checkpoint_id FROM checkpoints WHERE thread_id = :thread_id LIMIT 1"),
            {"thread_id": pending.checkpoint_thread_id},
        )
    assert len(runs) == 1
    assert checkpoint.first() is None
    resumed = await workflow.resume_run(corpus.id, pending.id)
    assert resumed.id == pending.id
    assert resumed.checkpoint_thread_id == str(pending.id)
    assert resumed.status == "waiting_for_review"
    async with phase02.session_factory() as session:
        later = list(
            await session.scalars(select(WorkflowRun).where(WorkflowRun.corpus_id == corpus.id))
        )
        present = await session.execute(
            text("SELECT checkpoint_id FROM checkpoints WHERE thread_id = :thread_id LIMIT 1"),
            {"thread_id": pending.checkpoint_thread_id},
        )
    assert len(later) == 1
    assert present.first() is not None
    events = await workflow.list_events(corpus.id, pending.id)
    assert any(event.event_type == "checkpoint_missing_reinitialized" for event in events)
    async with phase02.session_factory() as session, session.begin():
        await session.execute(
            text("DELETE FROM checkpoint_writes WHERE thread_id = :thread_id"),
            {"thread_id": pending.checkpoint_thread_id},
        )
        await session.execute(
            text("DELETE FROM checkpoint_blobs WHERE thread_id = :thread_id"),
            {"thread_id": pending.checkpoint_thread_id},
        )
        await session.execute(
            text("DELETE FROM checkpoints WHERE thread_id = :thread_id"),
            {"thread_id": pending.checkpoint_thread_id},
        )
    async with phase02.session_factory() as session:
        missing = await session.execute(
            text("SELECT checkpoint_id FROM checkpoints WHERE thread_id = :thread_id LIMIT 1"),
            {"thread_id": pending.checkpoint_thread_id},
        )
    assert missing.first() is None
    restarted = await workflow.resume_run(corpus.id, pending.id)
    assert restarted.id == pending.id
    assert restarted.checkpoint_thread_id == str(pending.id)
    assert restarted.status == "waiting_for_review"
    later_events = await workflow.list_events(corpus.id, pending.id)
    understand_completed = [
        event
        for event in later_events
        if event.event_type == "stage_completed" and event.stage_name == "understand"
    ]
    missing_events = [
        event for event in later_events if event.event_type == "checkpoint_missing_reinitialized"
    ]
    assert len(understand_completed) == 1
    assert len(missing_events) == 2
    async with phase02.session_factory() as session:
        run_rows = list(
            await session.scalars(select(WorkflowRun).where(WorkflowRun.corpus_id == corpus.id))
        )
    assert len(run_rows) == 1


async def _gather_runs(
    workflow: WorkflowService, corpus_id: object
) -> tuple[WorkflowRun, WorkflowRun]:
    first, second = await asyncio.gather(
        workflow.create_run(corpus_id),  # type: ignore[arg-type]
        workflow.create_run(corpus_id),  # type: ignore[arg-type]
    )
    return first, second


async def _probe_result() -> dict[str, object]:
    return {"ok": True}


async def _should_not_run() -> dict[str, object]:
    raise AssertionError("provider must not be called for a durable completed operation")


class _FailThenSucceedAdapter:
    mode: Literal["deterministic", "openai"] = "deterministic"
    model_name = "deterministic-local"

    def __init__(self) -> None:
        self.inner = CountingModelAdapter()
        self.calls = 0

    async def classify_blocks(self, blocks: Sequence[BlockContext]) -> ClassificationBatch:
        self.calls += 1
        if self.calls == 1:
            raise ModelError(
                "model_unavailable",
                "The model provider could not be reached.",
                "Retry the workflow run.",
                retryable=True,
                attempt_count=2,
            )
        return await self.inner.classify_blocks(blocks)

    async def extract_facts(self, blocks: Sequence[BlockContext]) -> ExtractionBatch:
        return await self.inner.extract_facts(blocks)

"""Durable LangGraph orchestration over Understand, Examine, and human review."""

from __future__ import annotations

import time
from typing import Any, TypedDict, cast
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select

from app.db import SessionFactory
from app.errors import ModelError, NotFoundError, Phase02Error
from app.examine_service import ExamineService
from app.model_gateway import PROMPT_CONFIG_VERSION, ModelAdapter
from app.models import AnalysisRun, DurableOperation, WorkflowRun, WorkflowRunEvent
from app.operation_ledger import DurableModelAdapter, OperationLedger, sha256_hex
from app.review_service import ReviewService
from app.services import Phase02Service
from app.taxonomy import GRAPH_VERSION, TAXONOMY_VERSION
from app.understand_graph import utcnow
from app.understand_service import UnderstandService
from app.workflow_barriers import hold_after_checkpoint

WORKFLOW_GRAPH_VERSION = "durable-workflow.v1"


class WorkflowState(TypedDict, total=False):
    corpus_id: str
    workflow_run_id: str
    analysis_run_id: str
    examination_run_id: str
    review_session_id: str
    current_stage: str
    status: str
    error_code: str
    error_detail: str
    error_action: str


class DurableWorkflow:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        examine: ExamineService,
        review: ReviewService,
        adapter: ModelAdapter,
        ledger: OperationLedger,
        checkpointer: BaseCheckpointSaver[Any],
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.examine = examine
        self.review = review
        self.adapter = adapter
        self.ledger = ledger
        graph = StateGraph(WorkflowState)
        graph.add_node("understand", self.understand)
        graph.add_node("after_understand", self.after_understand)
        graph.add_node("examine", self.examine_stage)
        graph.add_node("after_examine", self.after_examine)
        graph.add_node("open_review", self.open_review)
        graph.add_node("wait_for_review", self.wait_for_review)
        graph.add_node("finalize", self.finalize)
        graph.add_edge(START, "understand")
        graph.add_edge("understand", "after_understand")
        graph.add_edge("after_understand", "examine")
        graph.add_edge("examine", "after_examine")
        graph.add_edge("after_examine", "open_review")
        graph.add_edge("open_review", "wait_for_review")
        graph.add_edge("wait_for_review", "finalize")
        graph.add_edge("finalize", END)
        self.graph = graph.compile(checkpointer=checkpointer)

    def _understand_service(self, run: WorkflowRun) -> UnderstandService:
        source_input_version = str(run.configuration.get("source_input_version", ""))
        durable = DurableModelAdapter(
            self.adapter,
            self.ledger,
            corpus_id=run.corpus_id,
            workflow_run_id=run.id,
            source_input_version=source_input_version,
            taxonomy_version=str(run.configuration.get("taxonomy_version", TAXONOMY_VERSION)),
            understand_graph_version=str(
                run.configuration.get("understand_graph_version", GRAPH_VERSION)
            ),
            prompt_config_version=str(
                run.configuration.get("prompt_config_version", PROMPT_CONFIG_VERSION)
            ),
            workflow_graph_version=run.graph_version,
            reconcile_ambiguous=self.adapter.mode == "deterministic",
        )
        return UnderstandService(self.session_factory, self.phase02, durable)

    async def understand(self, state: WorkflowState) -> WorkflowState:
        started = time.perf_counter()
        run = await self._require_run(state)
        await self._set_stage(run.id, run.corpus_id, stage="understand", status="running")
        if run.analysis_run_id is not None:
            analysis = await self._get_analysis(run.corpus_id, run.analysis_run_id)
            if analysis is not None and analysis.status == "completed":
                await self._event(
                    run,
                    "stage_skipped",
                    stage="understand",
                    payload={"reason": "already_completed"},
                    duration_ms=_duration_ms(started),
                )
                return {
                    "analysis_run_id": str(analysis.id),
                    "current_stage": "understand",
                    "status": "running",
                }
            if analysis is not None and analysis.status == "running":
                await self._mark_analysis_interrupted(analysis)
                await self._event(
                    run,
                    "stage_recovered",
                    stage="understand",
                    payload={"reason": "incomplete_analysis_run"},
                    duration_ms=_duration_ms(started),
                )
            elif analysis is not None and analysis.status == "failed":
                await self._event(
                    run,
                    "stage_recovered",
                    stage="understand",
                    payload={
                        "reason": "failed_analysis_run",
                        "analysis_run_id": str(analysis.id),
                    },
                    duration_ms=_duration_ms(started),
                )
        try:
            analysis_run = await self._understand_service(run).create_run(run.corpus_id)
        except Phase02Error as error:
            await self._fail(run, error, stage="understand", started=started)
            raise
        await self._update_run(
            run.id,
            run.corpus_id,
            analysis_run_id=analysis_run.id,
            current_stage="understand",
            status="running",
        )
        if analysis_run.status != "completed":
            stage_error = ModelError(
                analysis_run.error_code or "understand_failed",
                analysis_run.error_detail or "Understand failed before completion.",
                "Resume the workflow run after correcting the recorded cause.",
                retryable=True,
                attempt_count=1,
            )
            await self._fail(run, stage_error, stage="understand", started=started)
            raise stage_error
        reused = await self._logical_ops(run.id, run.corpus_id)
        await self._event(
            run,
            "stage_completed",
            stage="understand",
            payload={
                "analysis_run_id": str(analysis_run.id),
                "analysis_status": analysis_run.status,
                "logical_operation_count": reused,
            },
            duration_ms=_duration_ms(started),
        )
        return {
            "analysis_run_id": str(analysis_run.id),
            "current_stage": "understand",
            "status": "running",
        }

    async def after_understand(self, state: WorkflowState) -> WorkflowState:
        run = await self._require_run(state)
        await hold_after_checkpoint(
            stage="understand",
            workflow_run_id=run.id,
            corpus_id=run.corpus_id,
        )
        return {}

    async def examine_stage(self, state: WorkflowState) -> WorkflowState:
        started = time.perf_counter()
        run = await self._require_run(state)
        await self._set_stage(run.id, run.corpus_id, stage="examine", status="running")
        if run.examination_run_id is not None:
            examination = await self.examine.get_run(run.corpus_id, run.examination_run_id)
            if examination.status == "completed":
                await self._event(
                    run,
                    "stage_skipped",
                    stage="examine",
                    payload={"reason": "already_completed"},
                    duration_ms=_duration_ms(started),
                )
                return {
                    "examination_run_id": str(examination.id),
                    "current_stage": "examine",
                }
        analysis_run_id = run.analysis_run_id or UUID(state["analysis_run_id"])
        try:
            examination = await self.examine.create_run(run.corpus_id, analysis_run_id)
        except Phase02Error as error:
            await self._fail(run, error, stage="examine", started=started)
            raise
        await self._update_run(
            run.id,
            run.corpus_id,
            examination_run_id=examination.id,
            current_stage="examine",
            status="running",
        )
        await self._event(
            run,
            "stage_completed",
            stage="examine",
            payload={"examination_run_id": str(examination.id)},
            duration_ms=_duration_ms(started),
        )
        return {
            "examination_run_id": str(examination.id),
            "current_stage": "examine",
        }

    async def after_examine(self, state: WorkflowState) -> WorkflowState:
        run = await self._require_run(state)
        await hold_after_checkpoint(
            stage="examine",
            workflow_run_id=run.id,
            corpus_id=run.corpus_id,
        )
        return {}

    async def open_review(self, state: WorkflowState) -> WorkflowState:
        started = time.perf_counter()
        run = await self._require_run(state)
        await self._set_stage(run.id, run.corpus_id, stage="open_review", status="running")
        examination_run_id = run.examination_run_id or UUID(state["examination_run_id"])
        try:
            session, created = await self.review.create_session(run.corpus_id, examination_run_id)
        except Phase02Error as error:
            await self._fail(run, error, stage="open_review", started=started)
            raise
        await self._update_run(
            run.id,
            run.corpus_id,
            review_session_id=session.id,
            current_stage="open_review",
            status="running",
        )
        await self._event(
            run,
            "stage_completed" if created else "stage_skipped",
            stage="open_review",
            payload={
                "review_session_id": str(session.id),
                "created": created,
                "auto_approved": False,
            },
            duration_ms=_duration_ms(started),
        )
        return {
            "review_session_id": str(session.id),
            "current_stage": "open_review",
        }

    async def wait_for_review(self, state: WorkflowState) -> WorkflowState:
        run = await self._require_run(state)
        session_id = run.review_session_id or UUID(state["review_session_id"])
        session = await self.review.get_session(run.corpus_id, session_id)
        if session.status == "completed":
            await self._event(
                run,
                "review_gate_passed",
                stage="wait_for_review",
                payload={"review_session_id": str(session.id)},
            )
            return {"current_stage": "wait_for_review", "status": "running"}
        await self._update_run(
            run.id,
            run.corpus_id,
            current_stage="wait_for_review",
            status="waiting_for_review",
        )
        await self._event(
            run,
            "waiting_for_review",
            stage="wait_for_review",
            payload={
                "review_session_id": str(session.id),
                "auto_approved": False,
                "pending_count": session.pending_count,
            },
        )
        interrupt(
            {
                "gate": "human_review",
                "status": "waiting_for_review",
                "review_session_id": str(session.id),
            }
        )
        session = await self.review.get_session(run.corpus_id, session_id)
        if session.status != "completed":
            await self._update_run(
                run.id,
                run.corpus_id,
                current_stage="wait_for_review",
                status="waiting_for_review",
            )
            interrupt(
                {
                    "gate": "human_review",
                    "status": "waiting_for_review",
                    "review_session_id": str(session.id),
                    "still_pending": True,
                }
            )
        return {"current_stage": "wait_for_review", "status": "running"}

    async def finalize(self, state: WorkflowState) -> WorkflowState:
        started = time.perf_counter()
        run = await self._require_run(state)
        await self._update_run(
            run.id,
            run.corpus_id,
            current_stage="completed",
            status="completed",
            completed=True,
        )
        await self._event(
            run,
            "workflow_completed",
            stage="finalize",
            payload={"publication": False},
            duration_ms=_duration_ms(started),
        )
        return {"status": "completed", "current_stage": "completed"}

    async def _require_run(self, state: WorkflowState) -> WorkflowRun:
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["workflow_run_id"])
        async with self.session_factory() as session:
            run = await session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.id == run_id,
                    WorkflowRun.corpus_id == corpus_id,
                )
            )
        if run is None:
            raise NotFoundError(
                "workflow_run_not_found",
                "The workflow run was not found in this corpus.",
                "Create a workflow run for this corpus and retry.",
            )
        return run

    async def _get_analysis(self, corpus_id: UUID, analysis_run_id: UUID) -> AnalysisRun | None:
        async with self.session_factory() as session:
            return cast(
                AnalysisRun | None,
                await session.scalar(
                    select(AnalysisRun).where(
                        AnalysisRun.id == analysis_run_id,
                        AnalysisRun.corpus_id == corpus_id,
                    )
                ),
            )

    async def _mark_analysis_interrupted(self, analysis: AnalysisRun) -> None:
        async with self.session_factory() as session, session.begin():
            row = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == analysis.id,
                    AnalysisRun.corpus_id == analysis.corpus_id,
                )
            )
            if row is None or row.status == "completed":
                return
            row.status = "failed"
            row.findings_status = "failed"
            row.error_code = "interrupted"
            row.error_detail = "The process stopped before Understand finalized."
            row.completed_at = utcnow()

    async def _set_stage(self, run_id: UUID, corpus_id: UUID, *, stage: str, status: str) -> None:
        await self._update_run(run_id, corpus_id, current_stage=stage, status=status)

    async def _update_run(
        self,
        run_id: UUID,
        corpus_id: UUID,
        *,
        current_stage: str | None = None,
        status: str | None = None,
        analysis_run_id: UUID | None = None,
        examination_run_id: UUID | None = None,
        review_session_id: UUID | None = None,
        completed: bool = False,
        error: Phase02Error | None = None,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.id == run_id,
                    WorkflowRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                return
            if current_stage is not None:
                run.current_stage = current_stage
            if status is not None:
                run.status = status
            if analysis_run_id is not None:
                run.analysis_run_id = analysis_run_id
            if examination_run_id is not None:
                run.examination_run_id = examination_run_id
            if review_session_id is not None:
                run.review_session_id = review_session_id
            if error is not None:
                run.error_code = error.code
                run.error_detail = error.detail
                run.error_action = error.action
            if completed:
                run.completed_at = utcnow()
            run.updated_at = utcnow()

    async def _fail(
        self,
        run: WorkflowRun,
        error: Phase02Error,
        *,
        stage: str,
        started: float,
    ) -> None:
        await self._update_run(
            run.id,
            run.corpus_id,
            current_stage=stage,
            status="failed",
            error=error,
        )
        await self._event(
            run,
            "stage_failed",
            stage=stage,
            payload={"error_code": error.code, "error_detail": error.detail},
            duration_ms=_duration_ms(started),
        )

    async def _event(
        self,
        run: WorkflowRun,
        event_type: str,
        *,
        stage: str | None = None,
        payload: dict[str, object] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            session.add(
                WorkflowRunEvent(
                    corpus_id=run.corpus_id,
                    workflow_run_id=run.id,
                    event_type=event_type,
                    stage_name=stage,
                    payload=payload or {},
                    duration_ms=duration_ms,
                )
            )

    async def _logical_ops(self, run_id: UUID, corpus_id: UUID) -> int:
        async with self.session_factory() as session:
            rows = list(
                await session.scalars(
                    select(DurableOperation).where(
                        DurableOperation.workflow_run_id == run_id,
                        DurableOperation.corpus_id == corpus_id,
                    )
                )
            )
        return sum(item.logical_operation_count for item in rows)


def source_input_version(pairs: list[tuple[str, str]]) -> str:
    return sha256_hex("|".join(f"{source}:{digest}" for source, digest in sorted(pairs)))


def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def thread_config(thread_id: str) -> dict[str, object]:
    return {"configurable": {"thread_id": thread_id}}


def compile_durable_workflow(
    *,
    session_factory: SessionFactory,
    phase02: Phase02Service,
    examine: ExamineService,
    review: ReviewService,
    adapter: ModelAdapter,
    ledger: OperationLedger,
    checkpointer: BaseCheckpointSaver[Any],
) -> DurableWorkflow:
    return DurableWorkflow(
        session_factory=session_factory,
        phase02=phase02,
        examine=examine,
        review=review,
        adapter=adapter,
        ledger=ledger,
        checkpointer=checkpointer,
    )

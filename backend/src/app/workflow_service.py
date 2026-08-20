"""Corpus-scoped durable workflow start, inspect, and resume."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from langgraph.errors import GraphBubbleUp
from langgraph.types import Command
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.checkpointer import open_postgres_checkpointer
from app.config import Settings
from app.db import SessionFactory
from app.errors import NotFoundError, Phase02Error, ValidationError
from app.examine_service import ExamineService
from app.model_gateway import PROMPT_CONFIG_VERSION, ModelAdapter, create_model_adapter
from app.models import SourceVersion, WorkflowRun, WorkflowRunEvent
from app.operation_ledger import OperationLedger
from app.review_service import ReviewService
from app.ruleset import RULESET_VERSION
from app.services import Phase02Service
from app.taxonomy import GRAPH_VERSION, TAXONOMY_VERSION
from app.understand_graph import utcnow
from app.workflow_graph import (
    WORKFLOW_GRAPH_VERSION,
    WorkflowState,
    compile_durable_workflow,
    source_input_version,
    thread_config,
)


def workflow_run_lock_key(run_id: UUID) -> str:
    return f"workflow-run:{run_id}"


class WorkflowService:
    def __init__(
        self,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        examine: ExamineService,
        review: ReviewService,
        adapter: ModelAdapter | None = None,
        settings: Settings | None = None,
        database_url: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.examine = examine
        self.review = review
        self.settings = settings or Settings()
        self.adapter = adapter or create_model_adapter(self.settings)
        self.ledger = OperationLedger(session_factory)
        self.database_url = database_url or self.settings.sqlalchemy_database_url()

    def _engine(self) -> AsyncEngine:
        return cast(AsyncEngine, self.session_factory.kw["bind"])

    async def create_run(self, corpus_id: UUID) -> WorkflowRun:
        run = await self._create_pending_run(corpus_id)
        return await self._execute(run, resume=False)

    async def _create_pending_run(self, corpus_id: UUID) -> WorkflowRun:
        await self.phase02.get_corpus(corpus_id)
        fingerprint = await self._source_fingerprint(corpus_id)
        run_id = uuid4()
        run = WorkflowRun(
            id=run_id,
            corpus_id=corpus_id,
            status="pending",
            current_stage="pending",
            checkpoint_thread_id=str(run_id),
            attempt_count=0,
            resume_count=0,
            graph_version=WORKFLOW_GRAPH_VERSION,
            configuration={
                "taxonomy_version": TAXONOMY_VERSION,
                "understand_graph_version": GRAPH_VERSION,
                "prompt_config_version": PROMPT_CONFIG_VERSION,
                "ruleset_version": RULESET_VERSION,
                "workflow_graph_version": WORKFLOW_GRAPH_VERSION,
                "source_input_version": fingerprint,
                "model_provider": self.adapter.mode,
                "model_name": self.adapter.model_name,
            },
        )
        async with self.session_factory() as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)
        await self._event(
            run,
            "workflow_created",
            payload={"source_input_version": fingerprint},
        )
        return run

    async def get_run(self, corpus_id: UUID, run_id: UUID) -> WorkflowRun:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as session:
            run = await session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.id == run_id,
                    WorkflowRun.corpus_id == corpus_id,
                )
            )
        if run is None:
            raise _run_not_found()
        return run

    async def list_events(self, corpus_id: UUID, run_id: UUID) -> list[WorkflowRunEvent]:
        await self.get_run(corpus_id, run_id)
        async with self.session_factory() as session:
            events = await session.scalars(
                select(WorkflowRunEvent)
                .where(
                    WorkflowRunEvent.workflow_run_id == run_id,
                    WorkflowRunEvent.corpus_id == corpus_id,
                )
                .order_by(
                    WorkflowRunEvent.created_at,
                    WorkflowRunEvent.id,
                )
            )
            return list(events)

    async def resume_run(self, corpus_id: UUID, run_id: UUID) -> WorkflowRun:
        run = await self.get_run(corpus_id, run_id)
        if run.status == "completed":
            raise ValidationError(
                "workflow_run_already_completed",
                "The workflow run is already completed.",
                "Inspect the run instead of resuming a completed workflow.",
            )
        return await self._execute(run, resume=True)

    @asynccontextmanager
    async def _hold_run_lock(self, run_id: UUID) -> AsyncIterator[None]:
        """Hold a session-level advisory lock for one workflow run.

        The dedicated connection stays open across claim, checkpoint inspect,
        optional failed-thread reset, graph invoke, and final state update.
        `pg_advisory_lock` is session-scoped, so it survives ORM commits.
        """

        key = workflow_run_lock_key(run_id)
        async with self._engine().connect() as lock_conn:
            locked = await lock_conn.execution_options(isolation_level="AUTOCOMMIT")
            await locked.execute(
                text("SELECT pg_advisory_lock(hashtext(:key))"),
                {"key": key},
            )
            try:
                yield
            finally:
                await locked.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:key))"),
                    {"key": key},
                )

    async def _execute(self, run: WorkflowRun, *, resume: bool) -> WorkflowRun:
        async with self._hold_run_lock(run.id):
            current = await self.get_run(run.corpus_id, run.id)
            previous_status = current.status
            previous_stage = current.current_stage
            claimed = await self._claim(current.corpus_id, current.id, resume=resume)
            await self._event(
                claimed,
                "workflow_resumed" if resume else "workflow_started",
                payload={
                    "resume_count": claimed.resume_count,
                    "attempt_count": claimed.attempt_count,
                },
            )
            async with open_postgres_checkpointer(self.database_url) as checkpointer:
                workflow = compile_durable_workflow(
                    session_factory=self.session_factory,
                    phase02=self.phase02,
                    examine=self.examine,
                    review=self.review,
                    adapter=self.adapter,
                    ledger=self.ledger,
                    checkpointer=checkpointer,
                )
                config: Any = thread_config(claimed.checkpoint_thread_id)
                payload: WorkflowState | Command[Any] | None
                invoke_graph = True
                if resume:
                    snapshot = await workflow.graph.aget_state(config)
                    has_checkpoint = await self._latest_checkpoint(claimed.checkpoint_thread_id)
                    if snapshot.interrupts:
                        if await self._human_review_completed(claimed):
                            payload = Command(resume={"gate": "human_review"})
                        else:
                            # Do not Command(resume) while required review is still pending.
                            # A second resume would otherwise consume the follow-up interrupt
                            # and finalize without a human decision.
                            invoke_graph = False
                            payload = None
                    elif previous_status == "failed":
                        # Same-run/thread restart from durable business state.
                        # Command(goto=) cannot revive ERROR pending writes.
                        await checkpointer.adelete_thread(claimed.checkpoint_thread_id)
                        payload = _canonical_graph_input(claimed)
                        await self._event(
                            claimed,
                            "checkpoint_reset_for_failed_resume",
                            payload={
                                "previous_stage": previous_stage,
                                "thread_id": claimed.checkpoint_thread_id,
                            },
                        )
                    elif not has_checkpoint:
                        payload = _canonical_graph_input(claimed)
                        await self._event(
                            claimed,
                            "checkpoint_missing_reinitialized",
                            payload={"thread_id": claimed.checkpoint_thread_id},
                        )
                    else:
                        payload = None
                else:
                    payload = _canonical_graph_input(claimed)
                durability: Literal["sync"] = "sync"
                try:
                    if invoke_graph:
                        await workflow.graph.ainvoke(payload, config, durability=durability)
                except GraphBubbleUp:
                    pass
                except Phase02Error:
                    pass
                except Exception:
                    failed = await self.get_run(claimed.corpus_id, claimed.id)
                    if failed.status in {"failed", "waiting_for_review"}:
                        pass
                    else:
                        raise
            latest = await self.get_run(claimed.corpus_id, claimed.id)
            snapshot_present = await self._latest_checkpoint(claimed.checkpoint_thread_id)
            if snapshot_present:
                await self._event(
                    latest,
                    "checkpoint_recorded",
                    payload={"thread_id": claimed.checkpoint_thread_id, "present": True},
                )
            return await self.get_run(claimed.corpus_id, claimed.id)

    async def _claim(self, corpus_id: UUID, run_id: UUID, *, resume: bool) -> WorkflowRun:
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(WorkflowRun)
                .where(WorkflowRun.id == run_id, WorkflowRun.corpus_id == corpus_id)
                .with_for_update()
            )
            if run is None:
                raise _run_not_found()
            if run.status == "completed":
                raise ValidationError(
                    "workflow_run_already_completed",
                    "The workflow run is already completed.",
                    "Inspect the run instead of resuming a completed workflow.",
                )
            run.attempt_count += 1
            if resume:
                # Count actual executions after the session lock, not arrivals.
                run.resume_count += 1
            if run.status == "failed":
                run.error_code = None
                run.error_detail = None
                run.error_action = None
            if run.status != "waiting_for_review":
                run.status = "running"
            run.started_at = run.started_at or utcnow()
            run.updated_at = utcnow()
            await session.flush()
            await session.refresh(run)
            return run

    async def _source_fingerprint(self, corpus_id: UUID) -> str:
        async with self.session_factory() as session:
            versions = list(
                await session.scalars(
                    select(SourceVersion)
                    .where(SourceVersion.corpus_id == corpus_id)
                    .order_by(SourceVersion.created_at.desc(), SourceVersion.id.desc())
                )
            )
        latest: dict[UUID, SourceVersion] = {}
        for version in versions:
            if version.source_id not in latest:
                latest[version.source_id] = version
        return source_input_version(
            [(str(item.source_id), item.sha256) for item in latest.values()]
        )

    async def _latest_checkpoint(self, thread_id: str) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                text("SELECT checkpoint_id FROM checkpoints WHERE thread_id = :thread_id LIMIT 1"),
                {"thread_id": thread_id},
            )
            return result.first() is not None

    async def _human_review_completed(self, run: WorkflowRun) -> bool:
        if run.review_session_id is None:
            return False
        session = await self.review.get_session(run.corpus_id, run.review_session_id)
        return session.status == "completed"

    async def _event(
        self,
        run: WorkflowRun,
        event_type: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            session.add(
                WorkflowRunEvent(
                    corpus_id=run.corpus_id,
                    workflow_run_id=run.id,
                    event_type=event_type,
                    payload=payload or {},
                )
            )


def _canonical_graph_input(run: WorkflowRun) -> WorkflowState:
    return {
        "corpus_id": str(run.corpus_id),
        "workflow_run_id": str(run.id),
        "current_stage": "pending",
        "status": "running",
    }


def _run_not_found() -> NotFoundError:
    return NotFoundError(
        "workflow_run_not_found",
        "The workflow run was not found in this corpus.",
        "Use a workflow run identifier returned for the same corpus.",
    )

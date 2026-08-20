"""Durable idempotency ledger for costly model/external operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar, cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import SessionFactory
from app.errors import ModelError
from app.model_gateway import (
    PROMPT_CONFIG_VERSION,
    BlockContext,
    ClassificationBatch,
    ExtractionBatch,
    ModelAdapter,
)
from app.models import DurableOperation
from app.taxonomy import GRAPH_VERSION, TAXONOMY_VERSION
from app.understand_graph import utcnow

T = TypeVar("T")

_AMBIGUOUS_STATUSES = frozenset({"in_flight", "ambiguous"})
_AMBIGUOUS_CODES = frozenset({"operation_ambiguous", "model_timeout_ambiguous"})


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def operation_identity_payload(
    *,
    workflow_run_id: UUID,
    stage: str,
    operation_type: str,
    source_input_version: str,
    request_hash: str,
    model_provider: str,
    model_name: str,
    taxonomy_version: str,
    understand_graph_version: str,
    prompt_config_version: str,
    workflow_graph_version: str,
) -> dict[str, str]:
    """Canonical fields that define one logical expensive operation.

    Runtime-only values such as timestamps are excluded.
    """

    return {
        "model_name": model_name,
        "model_provider": model_provider,
        "operation_type": operation_type,
        "prompt_config_version": prompt_config_version,
        "request_hash": request_hash,
        "source_input_version": source_input_version,
        "stage": stage,
        "taxonomy_version": taxonomy_version,
        "understand_graph_version": understand_graph_version,
        "workflow_graph_version": workflow_graph_version,
        "workflow_run_id": str(workflow_run_id),
    }


def make_operation_key(
    *,
    workflow_run_id: UUID,
    stage: str,
    operation_type: str,
    source_input_version: str,
    request_hash: str,
    model_provider: str,
    model_name: str,
    taxonomy_version: str,
    understand_graph_version: str,
    prompt_config_version: str,
    workflow_graph_version: str,
) -> str:
    return sha256_hex(
        canonical_json(
            operation_identity_payload(
                workflow_run_id=workflow_run_id,
                stage=stage,
                operation_type=operation_type,
                source_input_version=source_input_version,
                request_hash=request_hash,
                model_provider=model_provider,
                model_name=model_name,
                taxonomy_version=taxonomy_version,
                understand_graph_version=understand_graph_version,
                prompt_config_version=prompt_config_version,
                workflow_graph_version=workflow_graph_version,
            )
        )
    )


class OperationLedger:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def _engine(self) -> AsyncEngine:
        return cast(AsyncEngine, self.session_factory.kw["bind"])

    async def execute(
        self,
        *,
        corpus_id: UUID,
        workflow_run_id: UUID,
        stage: str,
        operation_type: str,
        source_input_version: str,
        request: object,
        model_provider: str,
        model_name: str,
        taxonomy_version: str,
        understand_graph_version: str,
        prompt_config_version: str,
        workflow_graph_version: str,
        fn: Callable[[], Awaitable[T]],
        dump: Callable[[T], dict[str, object]],
        restore: Callable[[dict[str, object]], T],
        reconcile_ambiguous: bool,
    ) -> T:
        request_hash = sha256_hex(canonical_json(request))
        operation_key = make_operation_key(
            workflow_run_id=workflow_run_id,
            stage=stage,
            operation_type=operation_type,
            source_input_version=source_input_version,
            request_hash=request_hash,
            model_provider=model_provider,
            model_name=model_name,
            taxonomy_version=taxonomy_version,
            understand_graph_version=understand_graph_version,
            prompt_config_version=prompt_config_version,
            workflow_graph_version=workflow_graph_version,
        )
        lock_key = f"durable-op:{operation_key}"
        async with self._engine().connect() as lock_conn:
            locked = await lock_conn.execution_options(isolation_level="AUTOCOMMIT")
            await locked.execute(
                text("SELECT pg_advisory_lock(hashtext(:key))"),
                {"key": lock_key},
            )
            try:
                async with self.session_factory() as session:
                    existing = await session.scalar(
                        select(DurableOperation).where(
                            DurableOperation.operation_key == operation_key
                        )
                    )
                    if existing is not None and existing.status == "completed":
                        return restore(existing.result_payload)
                    if existing is not None and existing.status in _AMBIGUOUS_STATUSES:
                        if existing.status == "in_flight":
                            existing.status = "ambiguous"
                            existing.updated_at = utcnow()
                            await session.commit()
                        if not reconcile_ambiguous:
                            raise ModelError(
                                "operation_ambiguous",
                                (
                                    "A prior provider call may have completed before "
                                    "the result was stored."
                                ),
                                (
                                    "Inspect the durable operation, then resume only "
                                    "with an explicit retry policy."
                                ),
                            )
                    if existing is None:
                        existing = DurableOperation(
                            corpus_id=corpus_id,
                            workflow_run_id=workflow_run_id,
                            operation_key=operation_key,
                            operation_type=operation_type,
                            stage=stage,
                            status="intended",
                            request_hash=request_hash,
                            result_payload={},
                            logical_operation_count=0,
                            provider_attempt_count=0,
                            provider_idempotency_id=operation_key,
                            source_input_version=source_input_version,
                            model_provider=model_provider,
                            model_name=model_name,
                            updated_at=utcnow(),
                        )
                        session.add(existing)
                        await session.commit()
                        await session.refresh(existing)
                    existing.status = "in_flight"
                    existing.provider_attempt_count += 1
                    existing.started_at = existing.started_at or utcnow()
                    existing.updated_at = utcnow()
                    await session.commit()
                    try:
                        result = await fn()
                    except ModelError as error:
                        row = await session.scalar(
                            select(DurableOperation).where(
                                DurableOperation.operation_key == operation_key
                            )
                        )
                        if row is not None:
                            reported = error.attempt_count if error.attempt_count is not None else 1
                            row.provider_attempt_count = max(row.provider_attempt_count, reported)
                            row.status = "ambiguous" if error.code in _AMBIGUOUS_CODES else "failed"
                            row.updated_at = utcnow()
                            row.completed_at = utcnow()
                            await session.commit()
                        raise
                    payload = dump(result)
                    row = await session.scalar(
                        select(DurableOperation).where(
                            DurableOperation.operation_key == operation_key
                        )
                    )
                    if row is None:
                        raise ModelError(
                            "operation_ledger_unavailable",
                            "The durable operation disappeared before the result could be stored.",
                            "Resume the workflow run after verifying PostgreSQL is reachable.",
                        )
                    row.status = "completed"
                    row.logical_operation_count = 1
                    row.provider_attempt_count = max(
                        row.provider_attempt_count,
                        _attempt_count(result, default=1),
                    )
                    row.result_payload = payload
                    row.result_hash = sha256_hex(canonical_json(payload))
                    row.updated_at = utcnow()
                    row.completed_at = utcnow()
                    await session.commit()
                    return result
            finally:
                await locked.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:key))"),
                    {"key": lock_key},
                )


def _attempt_count(result: object, *, default: int) -> int:
    usage = getattr(result, "usage", None)
    attempt_count = getattr(usage, "attempt_count", None)
    if isinstance(attempt_count, int) and attempt_count > 0:
        return attempt_count
    return default


class DurableModelAdapter:
    """Wrap a model adapter with a durable operation ledger."""

    def __init__(
        self,
        inner: ModelAdapter,
        ledger: OperationLedger,
        *,
        corpus_id: UUID,
        workflow_run_id: UUID,
        source_input_version: str,
        taxonomy_version: str,
        understand_graph_version: str,
        prompt_config_version: str,
        workflow_graph_version: str,
        reconcile_ambiguous: bool,
    ) -> None:
        self.inner = inner
        self.ledger = ledger
        self.corpus_id = corpus_id
        self.workflow_run_id = workflow_run_id
        self.source_input_version = source_input_version
        self.taxonomy_version = taxonomy_version
        self.understand_graph_version = understand_graph_version
        self.prompt_config_version = prompt_config_version
        self.workflow_graph_version = workflow_graph_version
        self.reconcile_ambiguous = reconcile_ambiguous
        self.mode = inner.mode
        self.model_name = inner.model_name

    async def classify_blocks(self, blocks: Sequence[BlockContext]) -> ClassificationBatch:
        request = [item.model_dump(mode="json") for item in blocks]
        return await self.ledger.execute(
            corpus_id=self.corpus_id,
            workflow_run_id=self.workflow_run_id,
            stage="understand",
            operation_type="classify",
            source_input_version=self.source_input_version,
            request=request,
            model_provider=self.mode,
            model_name=self.model_name,
            taxonomy_version=self.taxonomy_version,
            understand_graph_version=self.understand_graph_version,
            prompt_config_version=self.prompt_config_version,
            workflow_graph_version=self.workflow_graph_version,
            fn=lambda: self.inner.classify_blocks(blocks),
            dump=lambda batch: cast(dict[str, object], batch.model_dump(mode="json")),
            restore=lambda payload: ClassificationBatch.model_validate(payload),
            reconcile_ambiguous=self.reconcile_ambiguous,
        )

    async def extract_facts(self, blocks: Sequence[BlockContext]) -> ExtractionBatch:
        request = [item.model_dump(mode="json") for item in blocks]
        return await self.ledger.execute(
            corpus_id=self.corpus_id,
            workflow_run_id=self.workflow_run_id,
            stage="understand",
            operation_type="extract",
            source_input_version=self.source_input_version,
            request=request,
            model_provider=self.mode,
            model_name=self.model_name,
            taxonomy_version=self.taxonomy_version,
            understand_graph_version=self.understand_graph_version,
            prompt_config_version=self.prompt_config_version,
            workflow_graph_version=self.workflow_graph_version,
            fn=lambda: self.inner.extract_facts(blocks),
            dump=lambda batch: cast(dict[str, object], batch.model_dump(mode="json")),
            restore=lambda payload: ExtractionBatch.model_validate(payload),
            reconcile_ambiguous=self.reconcile_ambiguous,
        )


def default_identity_versions() -> dict[str, str]:
    from app.workflow_graph import WORKFLOW_GRAPH_VERSION

    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "understand_graph_version": GRAPH_VERSION,
        "prompt_config_version": PROMPT_CONFIG_VERSION,
        "workflow_graph_version": WORKFLOW_GRAPH_VERSION,
    }

from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from helpers import ingest_corpus, ledger_identity, make_workflow
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.errors import ModelError
from app.model_gateway import BlockContext, OpenAICompatibleAdapter
from app.models import DurableOperation
from app.operation_ledger import (
    DurableModelAdapter,
    OperationLedger,
    canonical_json,
    make_operation_key,
    sha256_hex,
)
from app.services import Phase02Service
from app.storage import LocalFileStorage


def _block() -> BlockContext:
    return BlockContext(
        source_block_id=uuid4(),
        source_version_id=uuid4(),
        source_sha256="a" * 64,
        format="txt",
        native_locator="lines[1-1]/block[0]",
        normalized_text="Project sponsor: A",
        block_type="paragraph",
    )


@pytest.mark.integration
async def test_attempt_intent_is_persisted_before_provider_call(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    run = await workflow.create_run(corpus.id)
    ledger = OperationLedger(phase02.session_factory)
    request = {"probe": "before-call"}
    seen: dict[str, object] = {}

    async def _observe() -> dict[str, object]:
        operation_key = make_operation_key(
            workflow_run_id=run.id,
            stage="understand",
            operation_type="before-call",
            source_input_version=str(run.configuration["source_input_version"]),
            request_hash=sha256_hex(canonical_json(request)),
            model_provider="deterministic",
            model_name="deterministic-local",
            **ledger_identity(run),
        )
        async with phase02.session_factory() as session:
            row = await session.scalar(
                select(DurableOperation).where(DurableOperation.operation_key == operation_key)
            )
        assert row is not None
        seen["status"] = row.status
        seen["attempts"] = row.provider_attempt_count
        return {"ok": True}

    result = await ledger.execute(
        corpus_id=corpus.id,
        workflow_run_id=run.id,
        stage="understand",
        operation_type="before-call",
        source_input_version=str(run.configuration["source_input_version"]),
        request=request,
        model_provider="deterministic",
        model_name="deterministic-local",
        **ledger_identity(run),
        fn=_observe,
        dump=lambda value: value,
        restore=lambda payload: payload,
        reconcile_ambiguous=True,
    )
    assert result == {"ok": True}
    assert seen["status"] == "in_flight"
    assert seen["attempts"] == 1
    async with phase02.session_factory() as session:
        stored = await session.scalar(
            select(DurableOperation).where(
                DurableOperation.workflow_run_id == run.id,
                DurableOperation.operation_type == "before-call",
            )
        )
    assert stored is not None
    assert stored.status == "completed"
    assert stored.logical_operation_count == 1
    assert stored.provider_attempt_count == 1
    assert stored.result_hash is not None


@pytest.mark.integration
async def test_failed_call_retains_attempt_count_started_before_provider(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    run = await workflow.create_run(corpus.id)
    ledger = OperationLedger(phase02.session_factory)

    async def _fail() -> dict[str, object]:
        raise ModelError(
            "model_unavailable",
            "The model provider could not be reached.",
            "Retry the workflow run.",
            retryable=True,
            attempt_count=1,
        )

    with pytest.raises(ModelError):
        await ledger.execute(
            corpus_id=corpus.id,
            workflow_run_id=run.id,
            stage="understand",
            operation_type="failed-call",
            source_input_version=str(run.configuration["source_input_version"]),
            request={"probe": "fail"},
            model_provider="deterministic",
            model_name="deterministic-local",
            **ledger_identity(run),
            fn=_fail,
            dump=lambda value: value,
            restore=lambda payload: payload,
            reconcile_ambiguous=True,
        )
    async with phase02.session_factory() as session:
        stored = await session.scalar(
            select(DurableOperation).where(
                DurableOperation.workflow_run_id == run.id,
                DurableOperation.operation_type == "failed-call",
            )
        )
    assert stored is not None
    assert stored.status == "failed"
    assert stored.logical_operation_count == 0
    assert stored.provider_attempt_count == 1


@pytest.mark.integration
async def test_uncertain_live_failure_through_ledger_is_ambiguous_and_not_retried(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    run = await workflow.create_run(corpus.id)
    kinds = (
        "read_timeout",
        "write_timeout",
        "timeout",
        "remote_protocol",
        "http_408",
        "http_504",
    )
    for kind in kinds:
        attempts = {"count": 0}

        def handler(
            _request: httpx.Request,
            captured: str = kind,
            captured_attempts: dict[str, int] = attempts,
        ) -> httpx.Response:
            captured_attempts["count"] += 1
            if captured == "read_timeout":
                raise httpx.ReadTimeout("slow")
            if captured == "write_timeout":
                raise httpx.WriteTimeout("slow")
            if captured == "timeout":
                raise httpx.TimeoutException("slow")
            if captured == "remote_protocol":
                raise httpx.RemoteProtocolError("server disconnected")
            status_code = 408 if captured == "http_408" else 504
            return httpx.Response(
                status_code,
                json={"error": "gateway", "secret": "sk-test-secret-should-not-leak"},
            )

        inner = OpenAICompatibleAdapter(
            api_key="sk-test-secret-should-not-leak",
            model="gpt-4o-mini",
            base_url="https://example.test/v1",
            timeout_seconds=0.1,
            max_retries=2,
            transport=httpx.MockTransport(handler),
        )
        durable = DurableModelAdapter(
            inner,
            OperationLedger(phase02.session_factory),
            corpus_id=corpus.id,
            workflow_run_id=run.id,
            source_input_version=str(run.configuration["source_input_version"]),
            taxonomy_version=str(run.configuration["taxonomy_version"]),
            understand_graph_version=str(run.configuration["understand_graph_version"]),
            prompt_config_version=str(run.configuration["prompt_config_version"]),
            workflow_graph_version=run.graph_version,
            reconcile_ambiguous=False,
        )
        with pytest.raises(ModelError) as error:
            await durable.classify_blocks([_block()])
        assert error.value.code == "operation_ambiguous"
        assert error.value.retryable is False
        assert attempts["count"] == 1
        assert "sk-test-secret-should-not-leak" not in error.value.detail
        assert "sk-test-secret-should-not-leak" not in (error.value.action or "")
    async with phase02.session_factory() as session:
        rows = list(
            await session.scalars(
                select(DurableOperation).where(
                    DurableOperation.workflow_run_id == run.id,
                    DurableOperation.status == "ambiguous",
                )
            )
        )
    assert len(rows) == len(kinds)
    assert all(row.provider_attempt_count >= 1 for row in rows)
    assert all(row.logical_operation_count == 0 for row in rows)


@pytest.mark.integration
async def test_malformed_http_200_through_ledger_is_terminal_and_not_retried(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    run = await workflow.create_run(corpus.id)
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    durable = DurableModelAdapter(
        OpenAICompatibleAdapter(
            api_key="sk-test-secret-should-not-leak",
            model="gpt-4o-mini",
            base_url="https://example.test/v1",
            timeout_seconds=0.1,
            max_retries=2,
            transport=httpx.MockTransport(handler),
        ),
        OperationLedger(phase02.session_factory),
        corpus_id=corpus.id,
        workflow_run_id=run.id,
        source_input_version=str(run.configuration["source_input_version"]),
        taxonomy_version=str(run.configuration["taxonomy_version"]),
        understand_graph_version=str(run.configuration["understand_graph_version"]),
        prompt_config_version=str(run.configuration["prompt_config_version"]),
        workflow_graph_version=run.graph_version,
        reconcile_ambiguous=False,
    )
    with pytest.raises(ModelError) as error:
        await durable.classify_blocks([_block()])
    assert error.value.code == "model_output_invalid"
    assert error.value.retryable is False
    assert attempts["count"] == 1
    async with phase02.session_factory() as session:
        stored = await session.scalar(
            select(DurableOperation).where(
                DurableOperation.workflow_run_id == run.id,
                DurableOperation.status == "failed",
                DurableOperation.operation_type == "classify",
            )
        )
    assert stored is not None
    assert stored.provider_attempt_count == 1
    assert stored.logical_operation_count == 0
    assert stored.result_hash is None


@pytest.mark.integration
async def test_invalid_durable_operation_states_are_rejected(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    run = await workflow.create_run(corpus.id)

    async def _insert(*, key: str, **values: object) -> None:
        payload = {
            "corpus_id": corpus.id,
            "workflow_run_id": run.id,
            "operation_key": key,
            "operation_type": "constraint",
            "stage": "understand",
            "request_hash": "b" * 64,
            "result_payload": {},
            "source_input_version": str(run.configuration["source_input_version"]),
            "model_provider": "deterministic",
            "model_name": "deterministic-local",
        }
        payload.update(values)
        async with phase02.session_factory() as session, session.begin():
            session.add(DurableOperation(**cast(dict[str, Any], payload)))

    with pytest.raises(IntegrityError):
        await _insert(
            key="c" * 64, status="completed", logical_operation_count=1, provider_attempt_count=1
        )
    with pytest.raises(IntegrityError):
        await _insert(
            key="d" * 64, status="in_flight", logical_operation_count=0, provider_attempt_count=0
        )
    with pytest.raises(IntegrityError):
        await _insert(
            key="e" * 64, status="ambiguous", logical_operation_count=0, provider_attempt_count=0
        )
    with pytest.raises(IntegrityError):
        await _insert(
            key="f" * 64, status="failed", logical_operation_count=1, provider_attempt_count=1
        )
    with pytest.raises(IntegrityError):
        await _insert(
            key="g" * 64, status="intended", logical_operation_count=0, provider_attempt_count=1
        )

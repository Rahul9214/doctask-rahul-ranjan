from pathlib import Path
from uuid import uuid4

import pytest
from helpers import CountingModelAdapter

from app.checkpointer import configure_windows_psycopg_loop, psycopg_conninfo
from app.model_gateway import PROMPT_CONFIG_VERSION
from app.operation_ledger import make_operation_key, sha256_hex
from app.taxonomy import GRAPH_VERSION, TAXONOMY_VERSION
from app.workflow_barriers import (
    BARRIER_PATH_ENV,
    HOLD_AFTER_ENV,
    RELEASE_PATH_ENV,
    hold_after_checkpoint,
)
from app.workflow_graph import WORKFLOW_GRAPH_VERSION


def test_windows_psycopg_loop_policy_is_safe_to_configure() -> None:
    configure_windows_psycopg_loop()


def test_psycopg_conninfo_strips_asyncpg_driver() -> None:
    converted = psycopg_conninfo(
        "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance_test"
    )
    assert converted.startswith("postgresql://")
    assert "asyncpg" not in converted
    assert "project_assurance_test" in converted


def test_operation_key_is_stable_and_changes_with_input() -> None:
    run_id = uuid4()

    def _key(
        *,
        request_hash: str = sha256_hex("blocks"),
        source_input_version: str = "abc",
        taxonomy_version: str = TAXONOMY_VERSION,
        understand_graph_version: str = GRAPH_VERSION,
        prompt_config_version: str = PROMPT_CONFIG_VERSION,
        workflow_graph_version: str = WORKFLOW_GRAPH_VERSION,
    ) -> str:
        return make_operation_key(
            workflow_run_id=run_id,
            stage="understand",
            operation_type="classify",
            source_input_version=source_input_version,
            request_hash=request_hash,
            model_provider="deterministic",
            model_name="deterministic-local",
            taxonomy_version=taxonomy_version,
            understand_graph_version=understand_graph_version,
            prompt_config_version=prompt_config_version,
            workflow_graph_version=workflow_graph_version,
        )

    first = _key()
    second = _key()
    assert first == second
    assert len(first) == 64
    assert first != _key(request_hash=sha256_hex("other"))
    assert first != _key(taxonomy_version="taxonomy.other")
    assert first != _key(understand_graph_version="understand.other")
    assert first != _key(prompt_config_version="prompt.other")
    assert first != _key(source_input_version="other-source")
    assert first != _key(workflow_graph_version="workflow.other")


@pytest.mark.asyncio
async def test_counting_adapter_retries_inside_provider_boundary() -> None:
    adapter = CountingModelAdapter(fail_classify_attempts=2)
    batch = await adapter.classify_blocks([])
    assert adapter.classify_operations == 1
    assert adapter.classify_attempts == 3
    assert batch.usage.operation_count == 1
    assert batch.usage.attempt_count == 3


@pytest.mark.asyncio
async def test_hold_after_checkpoint_returns_when_release_file_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = tmp_path / "barrier.json"
    release = tmp_path / "release"
    release.write_text("go", encoding="utf-8")
    monkeypatch.setenv(HOLD_AFTER_ENV, "understand")
    monkeypatch.setenv(BARRIER_PATH_ENV, str(barrier))
    monkeypatch.setenv(RELEASE_PATH_ENV, str(release))
    await hold_after_checkpoint(
        stage="understand",
        workflow_run_id=uuid4(),
        corpus_id=uuid4(),
    )
    assert barrier.exists()

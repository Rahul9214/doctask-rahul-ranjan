import os
import threading
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from helpers import (
    fixture_upload,
    ingest_corpus,
    make_workflow,
    prepare_incremental_corpus,
)
from sqlalchemy import select, text

from alembic import command
from app.config import get_settings
from app.models import DurableOperation
from app.services import Phase02Service
from app.storage import LocalFileStorage

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PHASE07_TABLES = (
    "incremental_runs",
    "incremental_artifact_evidence",
    "watcher_files",
    "corpus_revisions",
    "corpus_revision_sources",
)
PHASE06_TABLES = (
    "workflow_runs",
    "durable_operations",
    "workflow_run_events",
    "checkpoints",
)


def _migrate(direction: str, target: str) -> None:
    """Run Alembic against the test database without a second Python process.

    ``alembic.command`` calls ``asyncio.run`` via env.py, so this must run in a
    thread rather than inside the pytest event loop.
    """

    application_url = os.environ["DATABASE_URL"]
    test_url = os.environ["TEST_DATABASE_URL"]
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            os.environ["DATABASE_URL"] = test_url
            get_settings.cache_clear()
            config = Config(str(BACKEND_ROOT / "alembic.ini"))
            if direction == "downgrade":
                command.downgrade(config, target)
            elif direction == "upgrade":
                command.upgrade(config, target)
            else:
                raise ValueError(f"unsupported alembic direction {direction!r}")
        except BaseException as exc:
            errors.append(exc)
        finally:
            os.environ["DATABASE_URL"] = application_url
            get_settings.cache_clear()

    thread = threading.Thread(target=worker, name=f"alembic-{direction}")
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


def _changed_copy(src: Path, dest: Path, old: str, new: str) -> Path:
    dest.write_text(src.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    return dest


def _as_uuid_set(values: Iterable[object]) -> set[UUID]:
    return {UUID(str(item)) for item in values}


@pytest.mark.integration
async def test_populated_0007_downgrade_preserves_workflow_owned_ledger_rows(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    workflow_corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    workflow_run = await workflow.create_run(workflow_corpus.id)
    assert workflow_run.status == "waiting_for_review"

    harbor, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "harbor-ledger-modernization"
    )
    baseline = await incremental.get_current_revision(harbor.id)
    changed = _changed_copy(
        corpus_fixtures / "harbor-ledger-modernization" / "governance-notes.txt",
        tmp_path / "governance-notes.txt",
        "2026-12-04",
        "2026-12-18",
    )
    await phase02.ingest(
        corpus_id=harbor.id,
        logical_name="Governance Notes",
        declared_format="txt",
        upload=fixture_upload(changed, "txt"),
    )
    incremental_run = await incremental.create_run(harbor.id, baseline_revision_id=baseline.id)
    assert incremental_run.status == "completed"

    async with incremental.session_factory() as session:
        rows = list(await session.scalars(select(DurableOperation)))
        workflow_owned = [
            row
            for row in rows
            if row.workflow_run_id is not None and row.incremental_run_id is None
        ]
        incremental_owned = [
            row
            for row in rows
            if row.incremental_run_id is not None and row.workflow_run_id is None
        ]
    workflow_owned_ids = {row.id for row in workflow_owned}
    incremental_owned_ids = {row.id for row in incremental_owned}
    assert workflow_owned_ids, "Phase 06 workflow path must create workflow-owned ledger rows"
    assert incremental_owned_ids, (
        "Phase 07 incremental path must create incremental-owned ledger rows"
    )
    assert workflow_owned_ids.isdisjoint(incremental_owned_ids)
    assert {row.workflow_run_id for row in workflow_owned} == {workflow_run.id}
    assert {row.incremental_run_id for row in incremental_owned} == {incremental_run.id}

    try:
        _migrate("downgrade", "20260819_0006")
        async with incremental.session_factory() as session:
            remaining_ids = _as_uuid_set(
                await session.scalars(text("SELECT id FROM durable_operations"))
            )
            remaining_workflow_ids = _as_uuid_set(
                await session.scalars(
                    text("SELECT id FROM durable_operations WHERE workflow_run_id IS NOT NULL")
                )
            )
            incremental_column = await session.scalar(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'durable_operations' "
                    "AND column_name = 'incremental_run_id'"
                )
            )
            workflow_nullable = await session.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'durable_operations' "
                    "AND column_name = 'workflow_run_id'"
                )
            )
            phase07_present = {
                table: await session.scalar(text(f"SELECT to_regclass('public.{table}')"))
                for table in PHASE07_TABLES
            }
            phase06_present = {
                table: await session.scalar(text(f"SELECT to_regclass('public.{table}')"))
                for table in PHASE06_TABLES
            }
            surviving_workflow_run = await session.scalar(
                text("SELECT id FROM workflow_runs WHERE id = :run_id"),
                {"run_id": workflow_run.id},
            )
            surviving_checkpoint = await session.scalar(
                text("SELECT thread_id FROM checkpoints WHERE thread_id = :thread_id LIMIT 1"),
                {"thread_id": workflow_run.checkpoint_thread_id},
            )
            null_workflow_after = await session.scalar(
                text("SELECT COUNT(*) FROM durable_operations WHERE workflow_run_id IS NULL")
            )
            version = await session.scalar(text("SELECT version_num FROM alembic_version"))
        assert remaining_ids == workflow_owned_ids
        assert remaining_workflow_ids == workflow_owned_ids
        assert incremental_owned_ids.isdisjoint(remaining_ids)
        assert incremental_column is None
        assert workflow_nullable == "NO"
        assert all(value is None for value in phase07_present.values())
        assert all(value is not None for value in phase06_present.values())
        assert surviving_workflow_run == workflow_run.id
        assert surviving_checkpoint == workflow_run.checkpoint_thread_id
        assert int(null_workflow_after or 0) == 0
        assert version == "20260819_0006"
    finally:
        _migrate("upgrade", "20260819_0007")
        async with incremental.session_factory() as session:
            restored = await session.scalar(text("SELECT version_num FROM alembic_version"))
            surviving_after_upgrade = list(
                await session.scalars(
                    select(DurableOperation).where(DurableOperation.id.in_(workflow_owned_ids))
                )
            )
        assert restored == "20260819_0007"
        assert {row.id for row in surviving_after_upgrade} == workflow_owned_ids
        assert all(row.workflow_run_id == workflow_run.id for row in surviving_after_upgrade)
        assert all(row.incremental_run_id is None for row in surviving_after_upgrade)

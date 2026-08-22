from pathlib import Path
from uuid import UUID

import pytest
from helpers import (
    CountingModelAdapter,
    complete_required_review,
    fixture_upload,
    ingest_text,
    make_incremental,
    make_watcher,
)
from sqlalchemy import select

from app.models import SourceVersion
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
@pytest.mark.adversarial
async def test_one_source_incremental_avoids_full_rerun_and_copies_no_approvals(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    adapter = CountingModelAdapter()
    corpus = await phase02.create_corpus(
        name="Incremental Mini",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    first = await ingest_text(
        phase02,
        corpus.id,
        "Plan A",
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-10-30",
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Plan B",
        "Overall status is GREEN.\n\nProduction readiness baseline at 2026-11-14",
    )
    incremental = make_incremental(phase02, adapter)
    analysis = await incremental.understand.create_run(corpus.id)
    examination = await incremental.examine.create_run(corpus.id, analysis.id)
    session, _created = await incremental.review.create_session(corpus.id, examination.id)
    await complete_required_review(incremental.review, corpus.id, session.id)
    baseline = await incremental.create_baseline_revision(
        corpus.id,
        analysis_run_id=analysis.id,
        examination_run_id=examination.id,
        review_session_id=session.id,
    )
    versions_before = await _latest_versions(phase02, corpus.id)
    classify_before = adapter.classify_operations
    extract_before = adapter.extract_operations

    changed = tmp_path / "plan-a.txt"
    changed.write_text(
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-12-01",
        encoding="utf-8",
    )
    ingested = await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Plan A",
        declared_format="txt",
        upload=fixture_upload(changed, "txt"),
    )
    assert ingested.duplicate is False
    assert ingested.version.id != first.version.id
    unchanged = await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Plan A",
        declared_format="txt",
        upload=fixture_upload(changed, "txt"),
    )
    assert unchanged.duplicate is True
    assert unchanged.version.id == ingested.version.id

    run = await incremental.create_run(corpus.id, baseline_revision_id=baseline.id)
    assert run.status == "completed"
    evidence = await incremental.get_evidence(corpus.id, run.id)
    payload = evidence["evidence"]
    assert isinstance(payload, dict)
    assert payload["full_rerun"] is False
    executed = {str(item) for item in payload["classify_executed_source_version_ids"]}
    skipped = {str(item) for item in payload["classify_skipped_source_version_ids"]}
    assert str(ingested.version.id) in executed
    assert str(versions_before["Plan B"]) in skipped
    assert str(ingested.version.id) in {
        str(item) for item in payload["extract_executed_source_version_ids"]
    }
    assert (
        payload["classify_skipped_source_version_ids"]
        == payload["extract_skipped_source_version_ids"]
    )
    assert adapter.classify_operations > classify_before
    assert adapter.extract_operations > extract_before
    assert adapter.classify_operations - classify_before < 4

    assert run.review_session_id is not None
    new_items = await incremental.review.list_items(corpus.id, run.review_session_id)
    assert new_items
    assert all(item.review_status == "pending" for item in new_items)
    previous = await incremental.review.get_session(corpus.id, session.id)
    assert previous.status == "completed"

    stale = await incremental.create_run(corpus.id, baseline_revision_id=baseline.id)
    assert stale.status == "stale_baseline"
    current = await incremental.get_current_revision(corpus.id)
    assert current.id != baseline.id
    assert current.revision_number == baseline.revision_number + 1


@pytest.mark.integration
@pytest.mark.adversarial
async def test_watcher_retries_same_bytes_without_new_source_version(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Watcher Mini",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Decision Log",
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-10-30",
    )
    incremental = make_incremental(phase02)
    analysis = await incremental.understand.create_run(corpus.id)
    examination = await incremental.examine.create_run(corpus.id, analysis.id)
    session, _created = await incremental.review.create_session(corpus.id, examination.id)
    await complete_required_review(incremental.review, corpus.id, session.id)
    await incremental.create_baseline_revision(
        corpus.id,
        analysis_run_id=analysis.id,
        examination_run_id=examination.id,
        review_session_id=session.id,
    )
    before = await _version_count(phase02, corpus.id)
    inbox = tmp_path / "inbox"
    target_dir = inbox / str(corpus.id)
    target_dir.mkdir(parents=True)
    watcher = make_watcher(phase02, inbox, incremental=incremental, stable_polls=2)
    target = target_dir / "Decision Log.txt"
    target.write_text(
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-12-01",
        encoding="utf-8",
    )
    await watcher.poll_once()
    incremental.fail_before_finalize = True
    second = await watcher.poll_once()
    incremental.fail_before_finalize = False
    assert any(event.status == "failed_retryable" for event in second.events)
    after_fail = await _version_count(phase02, corpus.id)
    retry = await watcher.poll_once()
    assert retry.triggered == 1
    after_retry = await _version_count(phase02, corpus.id)
    assert after_retry == after_fail == before + 1
    assert any(event.status == "completed" for event in retry.events)


async def _latest_versions(phase02: Phase02Service, corpus_id: UUID) -> dict[str, UUID]:
    sources = await phase02.list_sources(corpus_id)
    mapping: dict[str, UUID] = {}
    for source in sources:
        _source, versions = await phase02.get_source(corpus_id, source.id)
        mapping[source.logical_name] = versions[-1].id
    return mapping


async def _version_count(phase02: Phase02Service, corpus_id: UUID) -> int:
    async with phase02.session_factory() as session:
        rows = list(
            await session.scalars(select(SourceVersion).where(SourceVersion.corpus_id == corpus_id))
        )
    return len(rows)

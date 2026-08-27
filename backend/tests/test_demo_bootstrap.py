from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from helpers import (
    complete_required_review,
    ingest_corpus,
    ingest_text,
    ingest_workflow_corpus,
    make_incremental,
    make_workflow,
)
from sqlalchemy import func, select

from app.demo_bootstrap import DemoBootstrap
from app.errors import NotFoundError, ProvenanceError, StorageError, ValidationError
from app.main import create_app
from app.models import Source, SourceVersion, WorkflowRun
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_bootstrapped_corpus_has_current_revision_and_rerun_is_idempotent(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    incremental = make_incremental(phase02)
    bootstrap = DemoBootstrap(phase02, incremental, fixture_root=corpus_fixtures)
    first = await bootstrap.bootstrap()
    names = {item.name for item in first}
    assert names == {"Aurora Control Hub", "Harbor Ledger Modernization"}
    assert all(item.created_corpus for item in first)
    assert all(item.created_revision for item in first)
    assert all(item.sources_ingested == 4 for item in first)
    assert all(item.sources_reused == 0 for item in first)
    assert all(item.sources_repaired == 0 for item in first)
    for item in first:
        revision = await incremental.get_current_revision(item.corpus_id)
        assert revision.id == item.revision_id
        assert revision.is_current is True
        sources = await phase02.list_sources(item.corpus_id)
        assert len(sources) == 4

    second = await bootstrap.bootstrap()
    assert {item.corpus_id for item in second} == {item.corpus_id for item in first}
    assert {item.revision_id for item in second} == {item.revision_id for item in first}
    assert all(not item.created_corpus for item in second)
    assert all(not item.created_revision for item in second)
    assert all(item.sources_ingested == 0 for item in second)
    assert all(item.sources_reused == 4 for item in second)
    assert all(item.sources_repaired == 0 for item in second)
    async with phase02.session_factory() as session:
        source_count = await session.scalar(select(func.count()).select_from(Source))
        version_count = await session.scalar(select(func.count()).select_from(SourceVersion))
    assert source_count == 8
    assert version_count == 8


@pytest.mark.integration
async def test_bootstrap_repairs_legacy_demo_corpus_without_duplicating_sources(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    legacy = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    incremental = make_incremental(phase02)
    with pytest.raises(NotFoundError) as missing:
        await incremental.get_current_revision(legacy.id)
    assert missing.value.code == "corpus_revision_not_found"

    results = await DemoBootstrap(phase02, incremental, fixture_root=corpus_fixtures).bootstrap()
    repaired = next(item for item in results if item.corpus_id == legacy.id)
    assert repaired.created_corpus is False
    assert repaired.created_revision is True
    assert repaired.sources_ingested == 0
    assert repaired.sources_reused == 4
    assert repaired.sources_repaired == 0
    revision = await incremental.get_current_revision(legacy.id)
    assert revision.id == repaired.revision_id
    sources = await phase02.list_sources(legacy.id)
    assert len(sources) == 4
    async with phase02.session_factory() as session:
        versions = list(
            await session.scalars(select(SourceVersion).where(SourceVersion.corpus_id == legacy.id))
        )
    assert len(versions) == 4


@pytest.mark.integration
async def test_incomplete_corpus_cannot_create_a_doomed_workflow_run(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    with pytest.raises(ValidationError) as error:
        await workflow.create_run(corpus.id)
    assert error.value.code == "corpus_revision_required"
    async with phase02.session_factory() as session:
        runs = list(
            await session.scalars(select(WorkflowRun).where(WorkflowRun.corpus_id == corpus.id))
        )
    assert runs == []

    application = create_app(
        phase02_service=phase02,
        understand_service=workflow.examine.understand,
        examine_service=workflow.examine,
        review_service=workflow.review,
        workflow_service=workflow,
        incremental_service=make_incremental(phase02, review=workflow.review),
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        created = await client.post(f"/corpora/{corpus.id}/workflow-runs")
        assert created.status_code == 400
        assert created.json()["code"] == "corpus_revision_required"
        current = await client.get(f"/corpora/{corpus.id}/revisions/current")
        assert current.status_code == 404
        assert current.json()["code"] == "corpus_revision_not_found"
    async with phase02.session_factory() as session:
        later = list(
            await session.scalars(select(WorkflowRun).where(WorkflowRun.corpus_id == corpus.id))
        )
    assert later == []


@pytest.mark.integration
async def test_workflow_starts_after_revision_and_resume_stays_run_specific(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_workflow_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    workflow = make_workflow(phase02)
    incremental = make_incremental(phase02, review=workflow.review)
    baseline = await incremental.get_current_revision(corpus.id)

    first = await workflow.create_run(corpus.id)
    assert first.status == "waiting_for_review"
    assert first.current_stage == "wait_for_review"
    assert first.analysis_run_id is not None
    assert first.examination_run_id is not None
    assert first.review_session_id is not None
    assert first.analysis_run_id != baseline.analysis_run_id

    second = await workflow.create_run(corpus.id)
    assert second.id != first.id
    assert second.status == "waiting_for_review"
    assert second.analysis_run_id != first.analysis_run_id
    assert second.review_session_id != first.review_session_id

    resumed_first = await workflow.resume_run(corpus.id, first.id)
    assert resumed_first.status == "waiting_for_review"
    assert resumed_first.id == first.id
    still_second = await workflow.get_run(corpus.id, second.id)
    assert still_second.status == "waiting_for_review"

    await complete_required_review(workflow.review, corpus.id, first.review_session_id)
    finished_first = await workflow.resume_run(corpus.id, first.id)
    assert finished_first.status == "completed"
    blocked_second = await workflow.resume_run(corpus.id, second.id)
    assert blocked_second.status == "waiting_for_review"
    assert blocked_second.id == second.id
    current = await incremental.get_current_revision(corpus.id)
    assert current.id == baseline.id

    application = create_app(
        phase02_service=phase02,
        understand_service=workflow.examine.understand,
        examine_service=workflow.examine,
        review_service=workflow.review,
        workflow_service=workflow,
        incremental_service=incremental,
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        current_http = await client.get(f"/corpora/{corpus.id}/revisions/current")
        assert current_http.status_code == 200
        assert current_http.json()["id"] == str(baseline.id)
        unknown = await client.post(f"/corpora/{uuid4()}/workflow-runs")
        assert unknown.status_code == 404


async def _source_versions(phase02: Phase02Service, corpus_id: UUID) -> list[SourceVersion]:
    versions: list[SourceVersion] = []
    for source in await phase02.list_sources(corpus_id):
        _source, source_versions = await phase02.get_source(corpus_id, source.id)
        versions.extend(source_versions)
    return versions


@pytest.mark.integration
async def test_bootstrap_repairs_missing_demo_bytes_without_new_versions(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    before = await _source_versions(phase02, corpus.id)
    assert len(before) == 4
    before_ids = {item.id for item in before}
    expected_sha = {item.id: item.sha256 for item in before}
    for version in before:
        storage.path_for_key(version.storage_key).unlink()

    bootstrap = DemoBootstrap(phase02, make_incremental(phase02), fixture_root=corpus_fixtures)
    first = await bootstrap.bootstrap_fixture(corpus_fixtures / "aurora-control-hub")
    repaired = first[0]
    assert repaired.corpus_id == corpus.id
    assert repaired.sources_ingested == 0
    assert repaired.sources_reused == 0
    assert repaired.sources_repaired == 4
    assert repaired.created_revision is True
    after = await _source_versions(phase02, corpus.id)
    assert {item.id for item in after} == before_ids
    for version in after:
        assert await storage.sha256_for_key(version.storage_key) == expected_sha[version.id]
        assert await storage.sha256_for_key(version.storage_key) == version.sha256

    second = await bootstrap.bootstrap_fixture(corpus_fixtures / "aurora-control-hub")
    assert second[0].sources_ingested == 0
    assert second[0].sources_reused == 4
    assert second[0].sources_repaired == 0
    assert second[0].revision_id == repaired.revision_id
    later = await _source_versions(phase02, corpus.id)
    assert len(later) == 4
    assert {item.id for item in later} == before_ids

    workflow = make_workflow(phase02)
    run = await workflow.create_run(corpus.id)
    assert run.status == "waiting_for_review"
    assert run.analysis_run_id is not None


@pytest.mark.integration
async def test_bootstrap_fails_when_demo_bytes_do_not_match_recorded_sha(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    versions = await _source_versions(phase02, corpus.id)
    storage.path_for_key(versions[0].storage_key).write_bytes(b"tampered demo bytes\n")
    bootstrap = DemoBootstrap(phase02, make_incremental(phase02), fixture_root=corpus_fixtures)
    with pytest.raises(ProvenanceError) as error:
        await bootstrap.bootstrap_fixture(corpus_fixtures / "aurora-control-hub")
    assert error.value.code == "source_bytes_tampered"
    assert await storage.sha256_for_key(versions[0].storage_key) != versions[0].sha256


@pytest.mark.integration
async def test_bootstrap_does_not_repair_non_demo_missing_source_bytes(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, storage = phase02_service
    other = await phase02.create_corpus(
        name="Operator Notes",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    ingested = await ingest_text(phase02, other.id, "Private Note", "keep this corpus distinct\n")
    storage.path_for_key(ingested.version.storage_key).unlink()

    await DemoBootstrap(
        phase02, make_incremental(phase02), fixture_root=corpus_fixtures
    ).bootstrap()
    with pytest.raises(StorageError) as missing:
        await storage.sha256_for_key(ingested.version.storage_key)
    assert missing.value.code == "source_bytes_unavailable"
    with pytest.raises(StorageError) as ingest_error:
        await ingest_text(phase02, other.id, "Private Note", "keep this corpus distinct\n")
    assert ingest_error.value.code == "source_bytes_unavailable"
    other_versions = await _source_versions(phase02, other.id)
    assert [item.id for item in other_versions] == [ingested.version.id]

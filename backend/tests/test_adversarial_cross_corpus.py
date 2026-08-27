from pathlib import Path
from typing import cast

import pytest
from helpers import (
    complete_required_review,
    ingest_corpus,
    ingest_workflow_corpus,
    make_examine,
    make_incremental,
    make_review,
    make_workflow,
)

from app.errors import NotFoundError
from app.parsers import SourceFormat
from app.schemas import CitationRequest
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
@pytest.mark.adversarial
async def test_aurora_and_harbor_cross_corpus_access_fails_closed(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_workflow_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    aurora_workflow = make_workflow(phase02)
    harbor_review = make_review(phase02)
    aurora_run = await aurora_workflow.create_run(aurora.id)
    harbor_analysis = await harbor_review.examine.understand.create_run(harbor.id)
    harbor_exam = await harbor_review.examine.create_run(harbor.id, harbor_analysis.id)
    harbor_session, _created = await harbor_review.create_session(harbor.id, harbor_exam.id)
    assert aurora_run.analysis_run_id is not None
    assert aurora_run.examination_run_id is not None
    assert aurora_run.review_session_id is not None

    with pytest.raises(NotFoundError) as workflow_cross:
        await aurora_workflow.get_run(harbor.id, aurora_run.id)
    assert workflow_cross.value.code == "workflow_run_not_found"
    assert "traceback" not in workflow_cross.value.detail.casefold()
    assert aurora.name not in workflow_cross.value.detail

    with pytest.raises(NotFoundError) as review_cross:
        await harbor_review.get_session(aurora.id, harbor_session.id)
    assert review_cross.value.code == "review_session_not_found"

    aurora_examine = make_examine(phase02)
    with pytest.raises(NotFoundError) as exam_cross:
        await aurora_examine.get_summary(aurora.id, harbor_exam.id)
    assert exam_cross.value.code == "examination_run_not_found"

    with pytest.raises(NotFoundError) as analysis_cross:
        await aurora_examine.understand.get_understanding(harbor.id, aurora_run.analysis_run_id)
    assert analysis_cross.value.code == "analysis_run_not_found"

    incremental = make_incremental(phase02, review=aurora_workflow.review)
    await complete_required_review(aurora_workflow.review, aurora.id, aurora_run.review_session_id)
    await complete_required_review(harbor_review, harbor.id, harbor_session.id)
    aurora_revision = await incremental.get_current_revision(aurora.id)
    harbor_incremental = make_incremental(phase02, review=harbor_review)
    harbor_revision = await harbor_incremental.create_baseline_revision(
        harbor.id,
        analysis_run_id=harbor_analysis.id,
        examination_run_id=harbor_exam.id,
        review_session_id=harbor_session.id,
    )
    aurora_inc_run = await incremental.create_run(aurora.id)
    harbor_inc_run = await harbor_incremental.create_run(harbor.id)
    assert aurora_revision.id != harbor_revision.id
    assert aurora_inc_run.id != harbor_inc_run.id

    with pytest.raises(NotFoundError) as harbor_revision_cross:
        await harbor_incremental.get_revision(harbor.id, aurora_revision.id)
    assert harbor_revision_cross.value.code == "corpus_revision_not_found"
    with pytest.raises(NotFoundError) as aurora_revision_cross:
        await incremental.get_revision(aurora.id, harbor_revision.id)
    assert aurora_revision_cross.value.code == "corpus_revision_not_found"
    with pytest.raises(NotFoundError) as harbor_run_cross:
        await harbor_incremental.get_run(harbor.id, aurora_inc_run.id)
    assert harbor_run_cross.value.code == "incremental_run_not_found"
    with pytest.raises(NotFoundError) as aurora_run_cross:
        await incremental.get_run(aurora.id, harbor_inc_run.id)
    assert aurora_run_cross.value.code == "incremental_run_not_found"

    sources = await phase02.list_sources(aurora.id)
    _source, versions = await phase02.get_source(aurora.id, sources[0].id)
    aurora_version = versions[0]
    aurora_blocks = await phase02.get_blocks(aurora.id, aurora_version.id)
    citation = CitationRequest(
        source_version_id=aurora_version.id,
        source_sha256=aurora_version.sha256,
        format=cast(SourceFormat, aurora_version.declared_format),
        native_locator=aurora_blocks[0].native_locator,
        normalized_start=0,
        normalized_end=max(1, min(8, len(aurora_blocks[0].normalized_text))),
        exact_quote=aurora_blocks[0].normalized_text[
            : max(1, min(8, len(aurora_blocks[0].normalized_text)))
        ],
    )
    with pytest.raises(NotFoundError) as citation_cross:
        await phase02.validate_citation(corpus_id=harbor.id, citation=citation)
    assert citation_cross.value.code == "source_version_not_found"
    assert aurora_blocks[0].normalized_text not in citation_cross.value.detail

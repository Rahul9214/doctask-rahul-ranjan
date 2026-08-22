from pathlib import Path
from uuid import UUID, uuid4

import pytest
from helpers import (
    complete_required_review,
    ingest_corpus,
    make_incremental,
    make_publication,
    make_workflow,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.canonical import canonical_hash
from app.examine_graph import utcnow
from app.models import (
    Contradiction,
    Fact,
    PublishedRegister,
    PublishedRegisterItem,
    PublishedRegisterItemContradiction,
    PublishedRegisterItemFact,
    ReviewItem,
)
from app.services import Phase02Service
from app.storage import LocalFileStorage


def _register(
    *,
    corpus_id: UUID,
    review_session_id: UUID,
    examination_run_id: UUID,
    analysis_run_id: UUID,
    corpus_revision_id: UUID | None = None,
    workflow_run_id: UUID | None = None,
) -> PublishedRegister:
    content_hash = canonical_hash({"invalid_integrity_probe": str(uuid4())})
    return PublishedRegister(
        id=uuid4(),
        corpus_id=corpus_id,
        publication_number=99,
        is_current=False,
        review_session_id=review_session_id,
        examination_run_id=examination_run_id,
        analysis_run_id=analysis_run_id,
        workflow_run_id=workflow_run_id,
        corpus_revision_id=corpus_revision_id,
        status="published",
        register_status="populated",
        version_identity=f"register.integrity.{content_hash[:12]}",
        content_sha256=content_hash,
        actor="integrity-test",
        publication_source="api",
        applied_count=0,
        rejected_omitted_count=0,
        pending_optional_omitted_count=0,
        edited_count=0,
        configuration={},
        published_at=utcnow(),
    )


@pytest.mark.integration
async def test_publication_database_rejects_same_corpus_cross_chain_references(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    publication = make_publication(phase02)
    review = publication.review

    analysis_one = await review.examine.understand.create_run(corpus.id)
    examination_one = await review.examine.create_run(corpus.id, analysis_one.id)
    session_one, _ = await review.create_session(corpus.id, examination_one.id)
    await complete_required_review(review, corpus.id, session_one.id)

    analysis_two = await review.examine.understand.create_run(corpus.id)
    examination_two = await review.examine.create_run(corpus.id, analysis_two.id)
    session_two, _ = await review.create_session(corpus.id, examination_two.id)
    await complete_required_review(review, corpus.id, session_two.id)
    revision_two = await make_incremental(
        phase02,
        review=review,
    ).create_baseline_revision(
        corpus.id,
        analysis_run_id=analysis_two.id,
        examination_run_id=examination_two.id,
        review_session_id=session_two.id,
    )

    async with phase02.session_factory() as db:
        db.add(
            _register(
                corpus_id=corpus.id,
                review_session_id=session_one.id,
                examination_run_id=examination_two.id,
                analysis_run_id=analysis_two.id,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    async with phase02.session_factory() as db:
        db.add(
            _register(
                corpus_id=corpus.id,
                review_session_id=session_one.id,
                examination_run_id=examination_one.id,
                analysis_run_id=analysis_one.id,
                corpus_revision_id=revision_two.id,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    published, created = await publication.publish(corpus.id, session_one.id)
    assert created is True
    async with phase02.session_factory() as db:
        source_item = await db.scalar(
            select(PublishedRegisterItem).where(
                PublishedRegisterItem.published_register_id == published.id,
                PublishedRegisterItem.review_status == "approved",
            )
        )
        assert source_item is not None
        wrong_finding_item = await db.scalar(
            select(ReviewItem).where(
                ReviewItem.review_session_id == session_one.id,
                ReviewItem.finding_id != source_item.finding_id,
            )
        )
        assert wrong_finding_item is not None
        db.add(
            PublishedRegisterItem(
                id=uuid4(),
                published_register_id=published.id,
                corpus_id=corpus.id,
                review_session_id=session_one.id,
                review_item_id=source_item.review_item_id,
                examination_run_id=examination_one.id,
                analysis_run_id=analysis_one.id,
                finding_id=wrong_finding_item.finding_id,
                rule_id="integrity.wrong-finding",
                rule_version="1",
                outcome="pass",
                severity="info",
                title="Invalid cross-linked item",
                message="Must fail database integrity.",
                structured_reason={},
                evidence_kind="grounded_facts",
                review_status="approved",
                content_origin="system_grounded",
                reviewer_authored_content=None,
                reviewer_authored_acknowledged=False,
                value_hash=canonical_hash({"invalid": "finding-link"}),
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


def _constraint_name(error: IntegrityError) -> str | None:
    current: BaseException | None = error
    while current is not None:
        constraint_name = getattr(current, "constraint_name", None)
        if isinstance(constraint_name, str):
            return constraint_name
        current = current.__cause__
    return None


@pytest.mark.integration
async def test_publication_database_rejects_unrelated_same_corpus_workflow(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    publication = make_publication(phase02)
    analysis = await publication.review.examine.understand.create_run(corpus.id)
    examination = await publication.review.examine.create_run(corpus.id, analysis.id)
    review, _ = await publication.review.create_session(corpus.id, examination.id)
    await complete_required_review(publication.review, corpus.id, review.id)

    unrelated_workflow = await make_workflow(
        phase02,
        review=publication.review,
    ).create_run(corpus.id)
    assert unrelated_workflow.analysis_run_id != analysis.id

    async with phase02.session_factory() as db:
        db.add(
            _register(
                corpus_id=corpus.id,
                review_session_id=review.id,
                examination_run_id=examination.id,
                analysis_run_id=analysis.id,
                workflow_run_id=unrelated_workflow.id,
            )
        )
        with pytest.raises(IntegrityError) as captured:
            await db.commit()
        assert _constraint_name(captured.value) == "fk_published_registers_workflow_chain"


@pytest.mark.integration
async def test_publication_database_rejects_cross_corpus_fact_evidence(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus_a = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    publication = make_publication(phase02)
    analysis_a = await publication.review.examine.understand.create_run(corpus_a.id)
    examination_a = await publication.review.examine.create_run(corpus_a.id, analysis_a.id)
    review_a, _ = await publication.review.create_session(corpus_a.id, examination_a.id)
    await complete_required_review(publication.review, corpus_a.id, review_a.id)
    published, _ = await publication.publish(corpus_a.id, review_a.id)

    corpus_b = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    analysis_b = await publication.review.examine.understand.create_run(corpus_b.id)
    async with phase02.session_factory() as db:
        item = await db.scalar(
            select(PublishedRegisterItem).where(
                PublishedRegisterItem.published_register_id == published.id
            )
        )
        fact_b = await db.scalar(
            select(Fact).where(
                Fact.corpus_id == corpus_b.id,
                Fact.run_id == analysis_b.id,
                Fact.support_status == "supported",
            )
        )
        assert item is not None
        assert fact_b is not None
        db.add(
            PublishedRegisterItemFact(
                published_item_id=item.id,
                published_register_id=published.id,
                corpus_id=corpus_a.id,
                analysis_run_id=analysis_a.id,
                fact_id=fact_b.id,
            )
        )
        with pytest.raises(IntegrityError) as captured:
            await db.commit()
        assert _constraint_name(captured.value) == "fk_published_item_facts_fact_run_corpus"


@pytest.mark.integration
async def test_publication_database_rejects_cross_corpus_contradiction_evidence(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus_a = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    publication = make_publication(phase02)
    analysis_a = await publication.review.examine.understand.create_run(corpus_a.id)
    examination_a = await publication.review.examine.create_run(corpus_a.id, analysis_a.id)
    review_a, _ = await publication.review.create_session(corpus_a.id, examination_a.id)
    await complete_required_review(publication.review, corpus_a.id, review_a.id)
    published, _ = await publication.publish(corpus_a.id, review_a.id)

    corpus_b = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    analysis_b = await publication.review.examine.understand.create_run(corpus_b.id)
    async with phase02.session_factory() as db:
        item = await db.scalar(
            select(PublishedRegisterItem).where(
                PublishedRegisterItem.published_register_id == published.id
            )
        )
        contradiction_b = await db.scalar(
            select(Contradiction).where(
                Contradiction.corpus_id == corpus_b.id,
                Contradiction.run_id == analysis_b.id,
            )
        )
        assert item is not None
        assert contradiction_b is not None
        db.add(
            PublishedRegisterItemContradiction(
                published_item_id=item.id,
                published_register_id=published.id,
                corpus_id=corpus_a.id,
                analysis_run_id=analysis_a.id,
                contradiction_id=contradiction_b.id,
            )
        )
        with pytest.raises(IntegrityError) as captured:
            await db.commit()
        assert _constraint_name(captured.value) == "fk_published_item_contradictions_contradiction"

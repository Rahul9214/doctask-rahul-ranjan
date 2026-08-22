from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from helpers import complete_required_review, ingest_corpus, make_publication
from sqlalchemy import and_, func, select
from sqlalchemy.orm.attributes import flag_modified

from app.errors import NotFoundError, ValidationError
from app.main import create_app
from app.models import (
    Contradiction,
    Fact,
    FindingContradictionEvidence,
    FindingFactEvidence,
    PublishedRegister,
    ReviewItem,
    SourceBlock,
    SourceVersion,
)
from app.publication_service import PublicationService
from app.services import Phase02Service
from app.storage import LocalFileStorage

Tamper = Callable[
    [Phase02Service, LocalFileStorage, UUID, UUID, UUID],
    Awaitable[str],
]


async def _completed_review(
    phase02: Phase02Service,
    corpus_fixtures: Path,
) -> tuple[PublicationService, UUID, UUID, UUID]:
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    publication = make_publication(phase02)
    analysis = await publication.review.examine.understand.create_run(corpus.id)
    examination = await publication.review.examine.create_run(corpus.id, analysis.id)
    review, _created = await publication.review.create_session(corpus.id, examination.id)
    await complete_required_review(publication.review, corpus.id, review.id)
    return publication, corpus.id, analysis.id, review.id


async def _publication_candidate_fact(
    phase02: Phase02Service,
    corpus_id: UUID,
    analysis_id: UUID,
    review_id: UUID,
) -> Fact:
    """Select evidence referenced by an applied item, never an unrelated analysis fact."""
    async with phase02.session_factory() as session:
        fact = await session.scalar(
            select(Fact)
            .join(
                FindingFactEvidence,
                and_(
                    FindingFactEvidence.fact_id == Fact.id,
                    FindingFactEvidence.analysis_run_id == Fact.run_id,
                    FindingFactEvidence.corpus_id == Fact.corpus_id,
                ),
            )
            .join(
                ReviewItem,
                and_(
                    ReviewItem.finding_id == FindingFactEvidence.finding_id,
                    ReviewItem.examination_run_id == FindingFactEvidence.examination_run_id,
                    ReviewItem.analysis_run_id == FindingFactEvidence.analysis_run_id,
                    ReviewItem.corpus_id == FindingFactEvidence.corpus_id,
                ),
            )
            .where(
                Fact.corpus_id == corpus_id,
                Fact.run_id == analysis_id,
                Fact.support_status == "supported",
                Fact.citation.is_not(None),
                ReviewItem.review_session_id == review_id,
                ReviewItem.review_status.in_(("approved", "edited")),
            )
            .order_by(ReviewItem.id, Fact.id)
        )
        assert fact is not None
        session.expunge(fact)
        return fact


async def _tamper_citation_json(
    phase02: Phase02Service,
    _storage: LocalFileStorage,
    corpus_id: UUID,
    analysis_id: UUID,
    review_id: UUID,
) -> str:
    sentinel = "tampered-publication-citation-sentinel"
    fact = await _publication_candidate_fact(phase02, corpus_id, analysis_id, review_id)
    async with phase02.session_factory() as session:
        row = await session.get(Fact, fact.id)
        assert row is not None
        citation = dict(row.citation or {})
        citation["exact_quote"] = sentinel
        row.citation = citation
        flag_modified(row, "citation")
        await session.commit()
    return sentinel


async def _tamper_source_bytes(
    phase02: Phase02Service,
    storage: LocalFileStorage,
    corpus_id: UUID,
    analysis_id: UUID,
    review_id: UUID,
) -> str:
    sentinel = "tampered-source-bytes-sentinel"
    fact = await _publication_candidate_fact(phase02, corpus_id, analysis_id, review_id)
    assert fact.citation is not None
    version_id = UUID(str(fact.citation["source_version_id"]))
    async with phase02.session_factory() as session:
        version = await session.get(SourceVersion, version_id)
        assert version is not None
    storage.path_for_key(version.storage_key).write_text(sentinel, encoding="utf-8")
    return sentinel


async def _tamper_source_block_binding(
    phase02: Phase02Service,
    _storage: LocalFileStorage,
    corpus_id: UUID,
    analysis_id: UUID,
    review_id: UUID,
) -> str:
    sentinel = "wrong-source-block-binding-sentinel"
    fact = await _publication_candidate_fact(phase02, corpus_id, analysis_id, review_id)
    async with phase02.session_factory() as session:
        other_block = await session.scalar(
            select(SourceBlock).where(
                SourceBlock.corpus_id == fact.corpus_id,
                SourceBlock.id != fact.source_block_id,
            )
        )
        assert other_block is not None
        row = await session.get(Fact, fact.id)
        assert row is not None
        row.source_block_id = other_block.id
        await session.commit()
    return sentinel


async def _tamper_contradiction_side(
    phase02: Phase02Service,
    _storage: LocalFileStorage,
    corpus_id: UUID,
    analysis_id: UUID,
    review_id: UUID,
) -> str:
    sentinel = "tampered-contradiction-side-sentinel"
    async with phase02.session_factory() as session:
        contradiction = await session.scalar(
            select(Contradiction)
            .join(
                FindingContradictionEvidence,
                and_(
                    FindingContradictionEvidence.contradiction_id == Contradiction.id,
                    FindingContradictionEvidence.analysis_run_id == Contradiction.run_id,
                    FindingContradictionEvidence.corpus_id == Contradiction.corpus_id,
                ),
            )
            .join(
                ReviewItem,
                and_(
                    ReviewItem.finding_id == FindingContradictionEvidence.finding_id,
                    ReviewItem.examination_run_id
                    == FindingContradictionEvidence.examination_run_id,
                    ReviewItem.analysis_run_id == FindingContradictionEvidence.analysis_run_id,
                    ReviewItem.corpus_id == FindingContradictionEvidence.corpus_id,
                ),
            )
            .where(
                Contradiction.run_id == analysis_id,
                Contradiction.corpus_id == corpus_id,
                ReviewItem.review_session_id == review_id,
                ReviewItem.review_status.in_(("approved", "edited")),
            )
        )
        assert contradiction is not None
        fact = await session.get(Fact, contradiction.fact_a_id)
        assert fact is not None
        citation = dict(fact.citation or {})
        citation["exact_quote"] = sentinel
        fact.citation = citation
        flag_modified(fact, "citation")
        await session.commit()
    return sentinel


@pytest.mark.integration
@pytest.mark.parametrize(
    "tamper",
    [
        _tamper_citation_json,
        _tamper_source_bytes,
        _tamper_source_block_binding,
        _tamper_contradiction_side,
    ],
    ids=[
        "persisted-citation-json",
        "immutable-source-bytes",
        "source-block-binding",
        "contradiction-side",
    ],
)
async def test_publication_revalidates_grounded_evidence_and_fails_closed(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tamper: Tamper,
) -> None:
    phase02, storage = phase02_service
    publication, corpus_id, analysis_id, review_id = await _completed_review(
        phase02, corpus_fixtures
    )
    sentinel = await tamper(phase02, storage, corpus_id, analysis_id, review_id)

    with pytest.raises(ValidationError) as error:
        await publication.publish(corpus_id, review_id)
    assert error.value.code == "publication_evidence_validation_failed"
    assert "traceback" not in error.value.detail.casefold()
    assert sentinel not in error.value.detail
    async with phase02.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(PublishedRegister))
    assert count == 0
    with pytest.raises(NotFoundError) as missing:
        await publication.get_current_register(corpus_id)
    assert missing.value.code == "publication_not_found"


@pytest.mark.integration
async def test_publication_revalidation_accepts_untampered_grounded_evidence(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    publication, corpus_id, _analysis_id, review_id = await _completed_review(
        phase02, corpus_fixtures
    )
    register, created = await publication.publish(corpus_id, review_id)
    assert created is True
    assert register.status == "published"
    assert register.items
    assert any(item.contradictions for item in register.items)


@pytest.mark.integration
async def test_publication_api_returns_controlled_error_for_tampered_evidence(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, storage = phase02_service
    publication, corpus_id, analysis_id, review_id = await _completed_review(
        phase02, corpus_fixtures
    )
    sentinel = await _tamper_citation_json(phase02, storage, corpus_id, analysis_id, review_id)
    application = create_app(
        phase02_service=phase02,
        understand_service=publication.review.examine.understand,
        examine_service=publication.review.examine,
        review_service=publication.review,
        publication_service=publication,
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        response = await client.post(f"/corpora/{corpus_id}/review-sessions/{review_id}/publish")
        assert response.status_code == 400
        assert response.json()["code"] == "publication_evidence_validation_failed"
        assert "traceback" not in response.text.casefold()
        assert sentinel not in response.text
        current = await client.get(f"/corpora/{corpus_id}/register")
        assert current.status_code == 404

import asyncio
from pathlib import Path

import pytest
from helpers import ingest_corpus, make_publication, make_review, mixed_review_then_complete

from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_concurrent_same_session_publication_is_idempotent(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    first = make_publication(phase02)
    second = make_publication(phase02, review=first.review)
    analysis = await first.review.examine.understand.create_run(corpus.id)
    exam = await first.review.examine.create_run(corpus.id, analysis.id)
    session, _created = await first.review.create_session(corpus.id, exam.id)
    await mixed_review_then_complete(first.review, corpus.id, session.id)
    left, right = await asyncio.gather(
        first.publish(corpus.id, session.id),
        second.publish(corpus.id, session.id),
    )
    left_register, _left_created = left
    right_register, _right_created = right
    assert left_register.id == right_register.id
    assert left_register.content_sha256 == right_register.content_sha256
    assert left_register.is_current is True
    current = await first.get_current_register(corpus.id)
    assert current.id == left_register.id


@pytest.mark.integration
async def test_concurrent_same_corpus_publications_keep_one_current(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    publication = make_publication(phase02)
    review = publication.review
    first_analysis = await review.examine.understand.create_run(corpus.id)
    first_exam = await review.examine.create_run(corpus.id, first_analysis.id)
    first_session, _created = await review.create_session(corpus.id, first_exam.id)
    await mixed_review_then_complete(review, corpus.id, first_session.id)
    second_analysis = await review.examine.understand.create_run(corpus.id)
    second_exam = await review.examine.create_run(corpus.id, second_analysis.id)
    second_session, _created = await review.create_session(corpus.id, second_exam.id)
    await mixed_review_then_complete(review, corpus.id, second_session.id)
    left, right = await asyncio.gather(
        publication.publish(corpus.id, first_session.id),
        make_publication(phase02, review=review).publish(corpus.id, second_session.id),
    )
    registers = {left[0].id, right[0].id}
    assert len(registers) == 2
    current = await publication.get_current_register(corpus.id)
    assert current.id in registers
    older = left[0] if left[0].id != current.id else right[0]
    fetched_older = await publication.get_register(corpus.id, older.id)
    assert fetched_older.is_current is False
    assert fetched_older.content_sha256 == older.content_sha256


@pytest.mark.integration
async def test_concurrent_distinct_corpus_publications_are_isolated(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    aurora_pub = make_publication(phase02)
    harbor_pub = make_publication(phase02, review=make_review(phase02))
    aurora_analysis = await aurora_pub.review.examine.understand.create_run(aurora.id)
    aurora_exam = await aurora_pub.review.examine.create_run(aurora.id, aurora_analysis.id)
    aurora_session, _ = await aurora_pub.review.create_session(aurora.id, aurora_exam.id)
    await mixed_review_then_complete(aurora_pub.review, aurora.id, aurora_session.id)
    harbor_analysis = await harbor_pub.review.examine.understand.create_run(harbor.id)
    harbor_exam = await harbor_pub.review.examine.create_run(harbor.id, harbor_analysis.id)
    harbor_session, _ = await harbor_pub.review.create_session(harbor.id, harbor_exam.id)
    await mixed_review_then_complete(harbor_pub.review, harbor.id, harbor_session.id)
    aurora_result, harbor_result = await asyncio.gather(
        aurora_pub.publish(aurora.id, aurora_session.id),
        harbor_pub.publish(harbor.id, harbor_session.id),
    )
    aurora_register, _ = aurora_result
    harbor_register, _ = harbor_result
    assert aurora_register.corpus_id == aurora.id
    assert harbor_register.corpus_id == harbor.id
    assert aurora_register.id != harbor_register.id
    aurora_rules = {item.rule_id for item in aurora_register.items}
    harbor_quotes = {
        citation.exact_quote for item in harbor_register.items for citation in item.citations
    }
    assert aurora_rules
    assert not any("Aurora Control Hub" in quote for quote in harbor_quotes)
    with pytest.raises(Exception) as error:
        await harbor_pub.get_register(harbor.id, aurora_register.id)
    assert getattr(error.value, "code", None) == "publication_not_found"

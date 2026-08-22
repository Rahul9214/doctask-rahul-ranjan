import pytest
from helpers import assert_controlled_error, ingest_text, make_examine, make_understand
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.errors import NotFoundError, ProvenanceError
from app.models import Fact, SourceBlock
from app.schemas import CitationRequest
from app.services import Phase02Service
from app.storage import LocalFileStorage


def _citation_payload(version_id: object, sha256: str, block: SourceBlock) -> dict[str, object]:
    quote = block.normalized_text[: min(12, len(block.normalized_text))]
    return {
        "source_version_id": version_id,
        "source_sha256": sha256,
        "format": "txt",
        "native_locator": block.native_locator,
        "normalized_start": 0,
        "normalized_end": len(quote),
        "exact_quote": quote,
    }


@pytest.mark.integration
@pytest.mark.adversarial
async def test_provenance_tamper_matrix_fails_closed(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Provenance Matrix",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    other = await phase02.create_corpus(
        name="Other Provenance",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    first = await ingest_text(
        phase02,
        corpus.id,
        "Memo",
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-10-30",
    )
    second = await ingest_text(
        phase02,
        corpus.id,
        "Memo",
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-12-01",
    )
    assert first.version.id != second.version.id
    blocks = await phase02.get_blocks(corpus.id, first.version.id)
    block = next(item for item in blocks if "Elena Marlow" in item.normalized_text)
    date_block = next(item for item in blocks if "2026-10-30" in item.normalized_text)
    valid = _citation_payload(first.version.id, first.version.sha256, block)
    valid_citation = CitationRequest.model_validate(valid)
    assert (await phase02.validate_citation(corpus_id=corpus.id, citation=valid_citation)).valid

    wrong_version = CitationRequest.model_validate(
        {**valid, "source_version_id": second.version.id}
    )
    with pytest.raises(ProvenanceError) as version_error:
        await phase02.validate_citation(corpus_id=corpus.id, citation=wrong_version)
    assert_controlled_error(version_error.value, code="source_sha_mismatch")

    wrong_sha = CitationRequest.model_validate({**valid, "source_sha256": "0" * 64})
    with pytest.raises(ProvenanceError) as sha_error:
        await phase02.validate_citation(corpus_id=corpus.id, citation=wrong_sha)
    assert_controlled_error(sha_error.value, code="source_sha_mismatch")

    wrong_locator = CitationRequest.model_validate(
        {**valid, "native_locator": "lines[999-999]/block[0]"}
    )
    with pytest.raises(ProvenanceError) as locator_error:
        await phase02.validate_citation(corpus_id=corpus.id, citation=wrong_locator)
    assert_controlled_error(locator_error.value, code="native_locator_mismatch")

    empty_span = {**valid, "normalized_start": 5, "normalized_end": 5, "exact_quote": "E"}
    empty_citation = CitationRequest.model_validate(empty_span)
    with pytest.raises(ProvenanceError) as empty_error:
        await phase02.validate_citation(corpus_id=corpus.id, citation=empty_citation)
    assert_controlled_error(empty_error.value, code="normalized_span_mismatch")

    closed = CitationRequest.model_validate(
        {
            **valid,
            "normalized_start": 0,
            "normalized_end": 1,
            "exact_quote": block.normalized_text[0:2],
        }
    )
    with pytest.raises(ProvenanceError) as closed_error:
        await phase02.validate_citation(corpus_id=corpus.id, citation=closed)
    assert_controlled_error(closed_error.value, code="exact_quote_mismatch")

    wrong_quote = CitationRequest.model_validate({**valid, "exact_quote": "not the stored quote"})
    with pytest.raises(ProvenanceError) as quote_error:
        await phase02.validate_citation(corpus_id=corpus.id, citation=wrong_quote)
    assert_controlled_error(
        quote_error.value, code="exact_quote_mismatch", leaked=block.normalized_text
    )

    with pytest.raises(NotFoundError) as cross_corpus:
        await phase02.validate_citation(corpus_id=other.id, citation=valid_citation)
    assert_controlled_error(cross_corpus.value, code="source_version_not_found")

    date_quote = "2026-10-30"
    date_start = date_block.normalized_text.index(date_quote)
    stale_after_change = CitationRequest.model_validate(
        {
            "source_version_id": second.version.id,
            "source_sha256": second.version.sha256,
            "format": "txt",
            "native_locator": date_block.native_locator,
            "normalized_start": date_start,
            "normalized_end": date_start + len(date_quote),
            "exact_quote": date_quote,
        }
    )
    with pytest.raises(ProvenanceError) as stale:
        await phase02.validate_citation(corpus_id=corpus.id, citation=stale_after_change)
    assert stale.value.code in {"native_locator_mismatch", "exact_quote_mismatch"}
    assert block.normalized_text not in stale.value.detail

    still_valid_old = await phase02.validate_citation(corpus_id=corpus.id, citation=valid_citation)
    assert still_valid_old.valid is True

    understand = make_understand(phase02)
    analysis = await understand.create_run(corpus.id)
    examine = make_examine(phase02, understand=understand)
    async with phase02.session_factory() as session:
        fact = await session.scalar(
            select(Fact).where(
                Fact.run_id == analysis.id,
                Fact.corpus_id == corpus.id,
                Fact.support_status == "supported",
            )
        )
        assert fact is not None
        citation = dict(fact.citation or {})
        citation["exact_quote"] = "tampered persisted citation json"
        fact.citation = citation
        flag_modified(fact, "citation")
        await session.commit()
    failed = await examine.create_run(corpus.id, analysis.id)
    assert failed.status == "failed"
    assert failed.error_code == "citation_revalidation_failed"
    assert failed.error_detail
    assert "traceback" not in failed.error_detail.casefold()
    assert "tampered persisted citation json" not in failed.error_detail
    assert list(storage.staging_root.iterdir()) == []

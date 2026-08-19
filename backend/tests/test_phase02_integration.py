import io
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import update
from starlette.datastructures import Headers

from app.errors import NotFoundError, ProvenanceError, ValidationError
from app.models import SourceBlock
from app.parsers import SourceFormat
from app.schemas import CitationRequest, SearchRequest
from app.services import Phase02Service
from app.storage import LocalFileStorage

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "markdown": "text/markdown",
    "txt": "text/plain",
}


def fixture_upload(path: Path, source_format: SourceFormat) -> UploadFile:
    return UploadFile(
        io.BytesIO(path.read_bytes()),
        filename=path.name,
        headers=Headers({"content-type": MEDIA_TYPES[source_format]}),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("source_format", "filename"),
    [
        ("pdf", "project-charter.pdf"),
        ("docx", "status-report.docx"),
        ("markdown", "risk-register.md"),
        ("txt", "decision-log.txt"),
    ],
)
async def test_each_format_citation_round_trip(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    source_format: SourceFormat,
    filename: str,
) -> None:
    service, _storage = phase02_service
    corpus = await service.create_corpus(
        name="Round trip",
        domain="software-project-assurance",
        declared_formats=["pdf", "docx", "markdown", "txt"],
    )
    result = await service.ingest(
        corpus_id=corpus.id,
        logical_name=f"{source_format} evidence",
        declared_format=source_format,
        upload=fixture_upload(corpus_fixtures / "aurora-control-hub" / filename, source_format),
    )
    block = (await service.get_blocks(corpus.id, result.version.id))[0]
    citation = CitationRequest(
        source_version_id=result.version.id,
        source_sha256=result.version.sha256,
        format=source_format,
        native_locator=block.native_locator,
        normalized_start=0,
        normalized_end=len(block.normalized_text),
        exact_quote=block.normalized_text,
    )

    validation = await service.validate_citation(corpus_id=corpus.id, citation=citation)

    assert validation.valid is True
    assert validation.source_block_id == block.id
    assert validation.resolved_quote == block.normalized_text
    assert result.version.parser_status == "parsed"
    assert result.block_count > 0
    assert len(block.embedding) == 64


@pytest.mark.integration
async def test_docx_table_cell_citation_round_trip(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    service, _storage = phase02_service
    corpus = await service.create_corpus(
        name="DOCX table citation",
        domain="software-project-assurance",
        declared_formats=["docx"],
    )
    result = await service.ingest(
        corpus_id=corpus.id,
        logical_name="Status Report",
        declared_format="docx",
        upload=fixture_upload(
            corpus_fixtures / "aurora-control-hub" / "status-report.docx",
            "docx",
        ),
    )
    block = next(
        candidate
        for candidate in await service.get_blocks(corpus.id, result.version.id)
        if candidate.block_type == "docx_table_cell"
    )
    citation = CitationRequest(
        source_version_id=result.version.id,
        source_sha256=result.version.sha256,
        format="docx",
        native_locator=block.native_locator,
        normalized_start=0,
        normalized_end=len(block.normalized_text),
        exact_quote=block.normalized_text,
    )

    validation = await service.validate_citation(corpus_id=corpus.id, citation=citation)

    assert validation.valid
    assert validation.source_block_id == block.id
    assert validation.resolved_quote == block.normalized_text
    assert block.native_locator.startswith("table[")


@pytest.mark.integration
async def test_immutable_versions_deduplicate_and_remain_corpus_scoped(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    service, _storage = phase02_service
    first_corpus = await service.create_corpus(
        name="First",
        domain="software-project-assurance",
        declared_formats=["markdown", "txt"],
    )
    second_corpus = await service.create_corpus(
        name="Second",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    source_path = corpus_fixtures / "aurora-control-hub" / "decision-log.txt"

    first = await service.ingest(
        corpus_id=first_corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=fixture_upload(source_path, "txt"),
    )
    duplicate = await service.ingest(
        corpus_id=first_corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=fixture_upload(source_path, "txt"),
    )
    conflicting_format_upload = UploadFile(
        io.BytesIO(source_path.read_bytes()),
        filename="decision-log.md",
        headers=Headers({"content-type": "text/markdown"}),
    )
    with pytest.raises(ValidationError) as format_error:
        await service.ingest(
            corpus_id=first_corpus.id,
            logical_name="Decision Log",
            declared_format="markdown",
            upload=conflicting_format_upload,
        )
    assert format_error.value.code == "duplicate_format_mismatch"

    changed_upload = UploadFile(
        io.BytesIO(source_path.read_bytes() + b"\nNew synthetic decision.\n"),
        filename="decision-log.txt",
        headers=Headers({"content-type": "text/plain"}),
    )
    changed = await service.ingest(
        corpus_id=first_corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=changed_upload,
    )
    other_corpus = await service.ingest(
        corpus_id=second_corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=fixture_upload(source_path, "txt"),
    )
    _source, versions = await service.get_source(first_corpus.id, first.source.id)

    assert duplicate.duplicate is True
    assert duplicate.version.id == first.version.id
    assert changed.version.id != first.version.id
    assert changed.version.sha256 != first.version.sha256
    assert len(versions) == 2
    assert other_corpus.version.id != first.version.id
    assert other_corpus.version.storage_key != first.version.storage_key


@pytest.mark.integration
async def test_provenance_rejects_every_tamper_and_scope_failure(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    service, storage = phase02_service
    corpus = await service.create_corpus(
        name="Tamper",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    other_corpus = await service.create_corpus(
        name="Other",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    result = await service.ingest(
        corpus_id=corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=fixture_upload(
            corpus_fixtures / "aurora-control-hub" / "decision-log.txt",
            "txt",
        ),
    )
    block = (await service.get_blocks(corpus.id, result.version.id))[0]
    valid = {
        "source_version_id": result.version.id,
        "source_sha256": result.version.sha256,
        "format": "txt",
        "native_locator": block.native_locator,
        "normalized_start": 0,
        "normalized_end": len(block.normalized_text),
        "exact_quote": block.normalized_text,
    }
    valid_citation = CitationRequest.model_validate(valid)
    assert (await service.validate_citation(corpus_id=corpus.id, citation=valid_citation)).valid

    wrong_sha = CitationRequest.model_validate({**valid, "source_sha256": "0" * 64})
    with pytest.raises(ProvenanceError) as sha_error:
        await service.validate_citation(corpus_id=corpus.id, citation=wrong_sha)
    assert sha_error.value.code == "source_sha_mismatch"

    wrong_format = CitationRequest.model_validate({**valid, "format": "markdown"})
    with pytest.raises(ProvenanceError) as format_error:
        await service.validate_citation(corpus_id=corpus.id, citation=wrong_format)
    assert format_error.value.code == "source_format_mismatch"

    wrong_locator = CitationRequest.model_validate(
        {**valid, "native_locator": "lines[999-999]/block[0]"}
    )
    with pytest.raises(ProvenanceError) as locator_error:
        await service.validate_citation(corpus_id=corpus.id, citation=wrong_locator)
    assert locator_error.value.code == "native_locator_mismatch"

    wrong_span = CitationRequest.model_validate(
        {**valid, "normalized_end": len(block.normalized_text) + 1}
    )
    with pytest.raises(ProvenanceError) as span_error:
        await service.validate_citation(corpus_id=corpus.id, citation=wrong_span)
    assert span_error.value.code == "normalized_span_mismatch"

    wrong_quote = CitationRequest.model_validate({**valid, "exact_quote": "wrong quote"})
    with pytest.raises(ProvenanceError) as quote_error:
        await service.validate_citation(corpus_id=corpus.id, citation=wrong_quote)
    assert quote_error.value.code == "exact_quote_mismatch"

    missing_version = CitationRequest.model_validate({**valid, "source_version_id": uuid4()})
    with pytest.raises(NotFoundError) as missing_error:
        await service.validate_citation(corpus_id=corpus.id, citation=missing_version)
    assert missing_error.value.code == "source_version_not_found"

    with pytest.raises(NotFoundError):
        await service.validate_citation(corpus_id=other_corpus.id, citation=valid_citation)

    tampered_text = ("X" if block.normalized_text[0] != "X" else "Y") + block.normalized_text[1:]
    async with service.session_factory() as session, session.begin():
        await session.execute(
            update(SourceBlock)
            .where(SourceBlock.id == block.id)
            .values(normalized_text=tampered_text)
        )
    with pytest.raises(ProvenanceError) as block_text_error:
        await service.validate_citation(corpus_id=corpus.id, citation=valid_citation)
    assert block_text_error.value.code == "source_block_integrity_mismatch"

    async with service.session_factory() as session, session.begin():
        await session.execute(
            update(SourceBlock)
            .where(SourceBlock.id == block.id)
            .values(
                normalized_text=block.normalized_text,
                native_locator="lines[999-999]/block[999]",
            )
        )
    with pytest.raises(ProvenanceError) as block_locator_error:
        await service.validate_citation(corpus_id=corpus.id, citation=valid_citation)
    assert block_locator_error.value.code == "source_block_integrity_mismatch"

    async with service.session_factory() as session, session.begin():
        await session.execute(
            update(SourceBlock)
            .where(SourceBlock.id == block.id)
            .values(native_locator=block.native_locator)
        )
    stored_path = storage.path_for_key(result.version.storage_key)
    stored_path.write_bytes(stored_path.read_bytes() + b"tampered")
    with pytest.raises(ProvenanceError) as tamper_error:
        await service.validate_citation(corpus_id=corpus.id, citation=valid_citation)
    assert tamper_error.value.code == "source_bytes_tampered"


@pytest.mark.integration
async def test_pgvector_similarity_is_persisted_filtered_and_corpus_scoped(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    service, _storage = phase02_service
    first_corpus = await service.create_corpus(
        name="Vectors A",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    second_corpus = await service.create_corpus(
        name="Vectors B",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )

    async def ingest_text(corpus_id: UUID, logical_name: str, content: str) -> None:
        upload = UploadFile(
            io.BytesIO(content.encode()),
            filename=f"{logical_name}.txt",
            headers=Headers({"content-type": "text/plain"}),
        )
        await service.ingest(
            corpus_id=corpus_id,
            logical_name=logical_name,
            declared_format="txt",
            upload=upload,
        )

    await ingest_text(first_corpus.id, "milestones", "delivery milestone owner status")
    await ingest_text(first_corpus.id, "fruit", "banana orange pear")
    await ingest_text(second_corpus.id, "private", "delivery milestone owner status")

    matches = await service.search(
        corpus_id=first_corpus.id,
        request=SearchRequest(query="delivery milestone", limit=5, declared_format="txt"),
    )

    assert matches
    assert "milestone" in matches[0].block.normalized_text
    assert all(match.block.corpus_id == first_corpus.id for match in matches)
    assert matches[0].score >= matches[-1].score


@pytest.mark.integration
async def test_retrieval_format_and_block_type_filters_exclude_other_blocks(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    service, _storage = phase02_service
    corpus = await service.create_corpus(
        name="Mixed retrieval",
        domain="software-project-assurance",
        declared_formats=["pdf", "docx", "markdown", "txt"],
    )
    fixtures: list[tuple[SourceFormat, str]] = [
        ("pdf", "project-charter.pdf"),
        ("docx", "status-report.docx"),
        ("markdown", "risk-register.md"),
        ("txt", "decision-log.txt"),
    ]
    versions: dict[SourceFormat, UUID] = {}
    for source_format, filename in fixtures:
        result = await service.ingest(
            corpus_id=corpus.id,
            logical_name=f"{source_format} source",
            declared_format=source_format,
            upload=fixture_upload(
                corpus_fixtures / "aurora-control-hub" / filename,
                source_format,
            ),
        )
        versions[source_format] = result.version.id

    txt_matches = await service.search(
        corpus_id=corpus.id,
        request=SearchRequest(
            query="owner decision milestone status risk",
            limit=20,
            declared_format="txt",
        ),
    )
    table_matches = await service.search(
        corpus_id=corpus.id,
        request=SearchRequest(
            query="milestone owner status",
            limit=20,
            block_type="docx_table_cell",
        ),
    )

    assert txt_matches
    assert all(match.block.source_version_id == versions["txt"] for match in txt_matches)
    assert all(
        match.block.source_version_id
        not in {
            versions["pdf"],
            versions["docx"],
            versions["markdown"],
        }
        for match in txt_matches
    )
    assert table_matches
    assert all(match.block.block_type == "docx_table_cell" for match in table_matches)
    assert all(match.block.source_version_id == versions["docx"] for match in table_matches)

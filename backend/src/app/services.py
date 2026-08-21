import asyncio
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionFactory
from app.embeddings import DeterministicEmbedding
from app.errors import NotFoundError, ProvenanceError, ValidationError
from app.models import Corpus, Source, SourceBlock, SourceVersion
from app.parsers import ParsedBlock, SourceFormat, parse_file, validate_declared_file
from app.schemas import CitationRequest, CitationValidationResponse, SearchRequest
from app.storage import LocalFileStorage


@dataclass(frozen=True, slots=True)
class IngestionResult:
    source: Source
    version: SourceVersion
    duplicate: bool
    block_count: int


@dataclass(frozen=True, slots=True)
class SearchMatch:
    block: SourceBlock
    score: float


class Phase02Service:
    def __init__(
        self,
        session_factory: SessionFactory,
        storage: LocalFileStorage,
        embedding: DeterministicEmbedding | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.embedding = embedding or DeterministicEmbedding()

    async def create_corpus(
        self, *, name: str, domain: str, declared_formats: list[SourceFormat]
    ) -> Corpus:
        corpus = Corpus(name=name, domain=domain, declared_formats=list(declared_formats))
        async with self.session_factory() as session:
            session.add(corpus)
            await session.commit()
            await session.refresh(corpus)
        return corpus

    async def get_corpus(self, corpus_id: UUID) -> Corpus:
        async with self.session_factory() as session:
            corpus = await session.get(Corpus, corpus_id)
            if corpus is None:
                raise _corpus_not_found()
            return corpus

    async def list_corpora(self, *, name: str | None = None) -> list[Corpus]:
        async with self.session_factory() as session:
            query: Select[tuple[Corpus]] = select(Corpus).order_by(Corpus.created_at, Corpus.id)
            if name is not None and name.strip():
                query = query.where(Corpus.name == name.strip())
            result = await session.scalars(query)
            return list(result)

    async def list_sources(self, corpus_id: UUID) -> list[Source]:
        async with self.session_factory() as session:
            if await session.get(Corpus, corpus_id) is None:
                raise _corpus_not_found()
            result = await session.scalars(
                select(Source)
                .where(Source.corpus_id == corpus_id)
                .order_by(Source.created_at, Source.id)
            )
            return list(result)

    async def get_source(
        self, corpus_id: UUID, source_id: UUID
    ) -> tuple[Source, list[SourceVersion]]:
        async with self.session_factory() as session:
            source = await session.scalar(
                select(Source).where(Source.id == source_id, Source.corpus_id == corpus_id)
            )
            if source is None:
                raise NotFoundError(
                    "source_not_found",
                    "The source was not found in this corpus.",
                    "Use a source identifier returned for the same corpus.",
                )
            versions = await session.scalars(
                select(SourceVersion)
                .where(
                    SourceVersion.source_id == source_id,
                    SourceVersion.corpus_id == corpus_id,
                )
                .order_by(SourceVersion.created_at, SourceVersion.id)
            )
            return source, list(versions)

    async def get_version(self, corpus_id: UUID, version_id: UUID) -> SourceVersion:
        async with self.session_factory() as session:
            version = await session.scalar(self._version_query(corpus_id, version_id))
            if version is None:
                raise _version_not_found()
            return version

    async def get_blocks(self, corpus_id: UUID, version_id: UUID) -> list[SourceBlock]:
        async with self.session_factory() as session:
            if await session.scalar(self._version_query(corpus_id, version_id)) is None:
                raise _version_not_found()
            blocks = await session.scalars(
                select(SourceBlock)
                .where(
                    SourceBlock.corpus_id == corpus_id,
                    SourceBlock.source_version_id == version_id,
                )
                .order_by(SourceBlock.block_index)
            )
            return list(blocks)

    async def ingest(
        self,
        *,
        corpus_id: UUID,
        logical_name: str,
        declared_format: SourceFormat,
        upload: UploadFile,
    ) -> IngestionResult:
        staged = await self.storage.stage(upload)
        promoted_key: str | None = None
        try:
            filename = upload.filename or ""
            validate_declared_file(
                staged.path,
                declared_format=declared_format,
                original_filename=filename,
                media_type=upload.content_type,
            )
            parsed_blocks = await asyncio.to_thread(parse_file, staged.path, declared_format)

            async with self.session_factory() as session:
                try:
                    async with session.begin():
                        corpus = await session.get(Corpus, corpus_id)
                        if corpus is None:
                            raise _corpus_not_found()
                        if declared_format not in corpus.declared_formats:
                            raise ValidationError(
                                "format_not_declared",
                                "This corpus does not allow the declared source format.",
                                "Use a format listed in the corpus declared_formats configuration.",
                            )

                        source = await session.scalar(
                            select(Source).where(
                                Source.corpus_id == corpus_id,
                                Source.logical_name == logical_name,
                            )
                        )
                        if source is None:
                            source = Source(corpus_id=corpus_id, logical_name=logical_name)
                            session.add(source)
                            await session.flush()

                        duplicate = await session.scalar(
                            select(SourceVersion).where(
                                SourceVersion.source_id == source.id,
                                SourceVersion.sha256 == staged.sha256,
                            )
                        )
                        if duplicate is not None:
                            if duplicate.declared_format != declared_format:
                                raise ValidationError(
                                    "duplicate_format_mismatch",
                                    "These bytes already exist under a different declared format.",
                                    "Use the original format or a different logical source.",
                                )
                            actual_sha = await self.storage.sha256_for_key(duplicate.storage_key)
                            if actual_sha != duplicate.sha256:
                                raise ProvenanceError(
                                    "source_bytes_tampered",
                                    "Stored source bytes no longer match the registered SHA-256.",
                                    "Restore the exact immutable source bytes; "
                                    "do not silently repair them.",
                                )
                            block_count = await self._block_count(session, duplicate.id, corpus_id)
                            return IngestionResult(source, duplicate, True, block_count)

                        version_id = uuid4()
                        storage_key = self.storage.storage_key(
                            corpus_id=corpus_id,
                            source_id=source.id,
                            version_id=version_id,
                            sha256=staged.sha256,
                            declared_format=declared_format,
                        )
                        await self.storage.promote(staged, storage_key)
                        promoted_key = storage_key

                        version = SourceVersion(
                            id=version_id,
                            source_id=source.id,
                            corpus_id=corpus_id,
                            sha256=staged.sha256,
                            media_type=_canonical_media_type(declared_format),
                            declared_format=declared_format,
                            original_filename=filename,
                            storage_key=storage_key,
                            byte_size=staged.byte_size,
                            parser_status="parsed",
                        )
                        session.add(version)
                        await session.flush()
                        for parsed in parsed_blocks:
                            session.add(
                                SourceBlock(
                                    source_version_id=version.id,
                                    corpus_id=corpus_id,
                                    block_index=parsed.block_index,
                                    block_type=parsed.block_type,
                                    native_locator=parsed.native_locator,
                                    normalized_text=parsed.normalized_text,
                                    normalized_start=parsed.normalized_start,
                                    normalized_end=parsed.normalized_end,
                                    embedding=self.embedding.embed(parsed.normalized_text),
                                    block_metadata=parsed.metadata,
                                )
                            )
                        await session.flush()
                except IntegrityError as error:
                    raise ValidationError(
                        "ingestion_conflict",
                        "A concurrent ingestion created conflicting source metadata.",
                        "Retry the upload; deduplication will reuse the durable version.",
                    ) from error

            return IngestionResult(source, version, False, len(parsed_blocks))
        except BaseException:
            if promoted_key is not None:
                await self.storage.remove_key(promoted_key)
            raise
        finally:
            await self.storage.remove_staged(staged)

    async def validate_citation(
        self, *, corpus_id: UUID, citation: CitationRequest
    ) -> CitationValidationResponse:
        async with self.session_factory() as session:
            version = await session.scalar(
                self._version_query(corpus_id, citation.source_version_id)
            )
            if version is None:
                raise _version_not_found()

            actual_sha = await self.storage.sha256_for_key(version.storage_key)
            if actual_sha != version.sha256:
                raise ProvenanceError(
                    "source_bytes_tampered",
                    "Stored source bytes no longer match the registered SHA-256.",
                    "Restore the exact immutable source bytes; do not silently repair them.",
                )
            if citation.source_sha256 != version.sha256:
                raise ProvenanceError(
                    "source_sha_mismatch",
                    "The citation SHA-256 does not match the immutable source version.",
                    "Use the SHA-256 returned for this source version.",
                )
            if citation.format != version.declared_format:
                raise ProvenanceError(
                    "source_format_mismatch",
                    "The citation format does not match the immutable source version.",
                    "Use the declared format returned for this source version.",
                )

            source_path = self.storage.path_for_key(version.storage_key)
            registered_format = citation.format
            fresh_blocks = await asyncio.to_thread(
                parse_file,
                source_path,
                registered_format,
            )
            if await self.storage.sha256_for_key(version.storage_key) != version.sha256:
                raise ProvenanceError(
                    "source_bytes_tampered",
                    "Stored source bytes changed while provenance was being resolved.",
                    "Restore the exact immutable source bytes; do not silently repair them.",
                )
            fresh_block = next(
                (
                    candidate
                    for candidate in fresh_blocks
                    if candidate.native_locator == citation.native_locator
                ),
                None,
            )
            if fresh_block is None:
                raise ProvenanceError(
                    "native_locator_mismatch",
                    "The citation locator does not resolve from the original source bytes.",
                    "Use a native_locator returned for this immutable source version.",
                )

            persisted_block = await session.scalar(
                select(SourceBlock).where(
                    SourceBlock.corpus_id == corpus_id,
                    SourceBlock.source_version_id == citation.source_version_id,
                    SourceBlock.native_locator == citation.native_locator,
                )
            )
            if persisted_block is None or not _persisted_block_matches_fresh(
                persisted_block, fresh_block
            ):
                raise ProvenanceError(
                    "source_block_integrity_mismatch",
                    "The persisted source block does not match a fresh parse of source bytes.",
                    "Restore coherent immutable block metadata from the original source version.",
                )
            if (
                citation.normalized_start < fresh_block.normalized_start
                or citation.normalized_end > fresh_block.normalized_end
                or citation.normalized_start >= citation.normalized_end
            ):
                raise ProvenanceError(
                    "normalized_span_mismatch",
                    "The citation span is outside the resolved normalized block.",
                    "Use a valid half-open character span within the normalized block.",
                )

            resolved_quote = fresh_block.normalized_text[
                citation.normalized_start : citation.normalized_end
            ]
            if resolved_quote != citation.exact_quote:
                raise ProvenanceError(
                    "exact_quote_mismatch",
                    "The exact quote does not match the resolved normalized span.",
                    "Copy the exact normalized text at the requested half-open span.",
                )
            return CitationValidationResponse(
                source_version_id=version.id,
                source_block_id=persisted_block.id,
                resolved_quote=resolved_quote,
            )

    async def search(self, *, corpus_id: UUID, request: SearchRequest) -> list[SearchMatch]:
        query_vector = self.embedding.embed(request.query)
        if not any(query_vector):
            raise ValidationError(
                "empty_search_terms",
                "The search query contains no indexable letters or numbers.",
                "Supply at least one word or number.",
            )
        distance_expression = SourceBlock.embedding.cosine_distance(query_vector)
        distance = distance_expression.label("distance")
        statement = (
            select(SourceBlock, distance)
            .join(SourceVersion, SourceVersion.id == SourceBlock.source_version_id)
            .where(
                SourceBlock.corpus_id == corpus_id,
                distance_expression.is_not(None),
            )
        )
        if request.block_type is not None:
            statement = statement.where(SourceBlock.block_type == request.block_type)
        if request.declared_format is not None:
            statement = statement.where(SourceVersion.declared_format == request.declared_format)
        statement = statement.order_by(distance, SourceBlock.block_index, SourceBlock.id).limit(
            request.limit
        )

        async with self.session_factory() as session:
            if await session.get(Corpus, corpus_id) is None:
                raise _corpus_not_found()
            rows = (await session.execute(statement)).all()
            return [
                SearchMatch(block=cast(SourceBlock, row[0]), score=1.0 - float(row[1]))
                for row in rows
            ]

    @staticmethod
    def _version_query(corpus_id: UUID, version_id: UUID) -> Select[tuple[SourceVersion]]:
        return select(SourceVersion).where(
            SourceVersion.id == version_id,
            SourceVersion.corpus_id == corpus_id,
        )

    @staticmethod
    async def _block_count(session: AsyncSession, version_id: UUID, corpus_id: UUID) -> int:
        blocks = await session.scalars(
            select(SourceBlock.id).where(
                SourceBlock.source_version_id == version_id,
                SourceBlock.corpus_id == corpus_id,
            )
        )
        return len(list(blocks))


def _canonical_media_type(declared_format: SourceFormat) -> str:
    return {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "markdown": "text/markdown",
        "txt": "text/plain",
    }[declared_format]


def _persisted_block_matches_fresh(
    persisted: SourceBlock,
    fresh: ParsedBlock,
) -> bool:
    return (
        persisted.block_index == fresh.block_index
        and persisted.block_type == fresh.block_type
        and persisted.native_locator == fresh.native_locator
        and persisted.normalized_text == fresh.normalized_text
        and persisted.normalized_start == fresh.normalized_start
        and persisted.normalized_end == fresh.normalized_end
        and persisted.block_metadata == fresh.metadata
    )


def _corpus_not_found() -> NotFoundError:
    return NotFoundError(
        "corpus_not_found",
        "The corpus was not found.",
        "Use a corpus identifier returned by POST /corpora.",
    )


def _version_not_found() -> NotFoundError:
    return NotFoundError(
        "source_version_not_found",
        "The source version was not found in this corpus.",
        "Use a source version identifier returned for the same corpus.",
    )

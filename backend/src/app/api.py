from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status

from app.parsers import SourceFormat
from app.schemas import (
    CitationRequest,
    CitationValidationResponse,
    CorpusCreate,
    CorpusResponse,
    IngestionResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SourceBlockResponse,
    SourceResponse,
    SourceSummaryResponse,
    SourceVersionResponse,
)
from app.services import Phase02Service

router = APIRouter()


def get_phase02_service(request: Request) -> Phase02Service:
    return cast(Phase02Service, request.app.state.phase02_service)


Service = Annotated[Phase02Service, Depends(get_phase02_service)]


@router.post("/corpora", response_model=CorpusResponse, status_code=status.HTTP_201_CREATED)
async def create_corpus(payload: CorpusCreate, service: Service) -> CorpusResponse:
    corpus = await service.create_corpus(
        name=payload.name,
        domain=payload.domain,
        declared_formats=payload.declared_formats,
    )
    return CorpusResponse.model_validate(corpus)


@router.get("/corpora/{corpus_id}", response_model=CorpusResponse)
async def get_corpus(corpus_id: UUID, service: Service) -> CorpusResponse:
    return CorpusResponse.model_validate(await service.get_corpus(corpus_id))


@router.get("/corpora/{corpus_id}/sources", response_model=list[SourceSummaryResponse])
async def list_sources(corpus_id: UUID, service: Service) -> list[SourceSummaryResponse]:
    return [
        SourceSummaryResponse.model_validate(source)
        for source in await service.list_sources(corpus_id)
    ]


@router.post(
    "/corpora/{corpus_id}/sources",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_source(
    corpus_id: UUID,
    response: Response,
    logical_name: Annotated[str, Form(min_length=1, max_length=255)],
    declared_format: Annotated[SourceFormat, Form()],
    file: Annotated[UploadFile, File()],
    service: Service,
) -> IngestionResponse:
    try:
        result = await service.ingest(
            corpus_id=corpus_id,
            logical_name=logical_name,
            declared_format=declared_format,
            upload=file,
        )
    finally:
        await file.close()
    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    return IngestionResponse(
        source=SourceSummaryResponse.model_validate(result.source),
        version=SourceVersionResponse.model_validate(result.version),
        duplicate=result.duplicate,
        block_count=result.block_count,
    )


@router.get("/corpora/{corpus_id}/sources/{source_id}", response_model=SourceResponse)
async def get_source(corpus_id: UUID, source_id: UUID, service: Service) -> SourceResponse:
    source, versions = await service.get_source(corpus_id, source_id)
    return SourceResponse(
        **SourceSummaryResponse.model_validate(source).model_dump(),
        versions=[SourceVersionResponse.model_validate(version) for version in versions],
    )


@router.get(
    "/corpora/{corpus_id}/source-versions/{version_id}",
    response_model=SourceVersionResponse,
)
async def get_source_version(
    corpus_id: UUID, version_id: UUID, service: Service
) -> SourceVersionResponse:
    return SourceVersionResponse.model_validate(await service.get_version(corpus_id, version_id))


@router.get(
    "/corpora/{corpus_id}/source-versions/{version_id}/blocks",
    response_model=list[SourceBlockResponse],
)
async def get_source_blocks(
    corpus_id: UUID, version_id: UUID, service: Service
) -> list[SourceBlockResponse]:
    return [
        SourceBlockResponse.model_validate(block)
        for block in await service.get_blocks(corpus_id, version_id)
    ]


@router.post(
    "/corpora/{corpus_id}/citations/validate",
    response_model=CitationValidationResponse,
)
async def validate_citation(
    corpus_id: UUID, payload: CitationRequest, service: Service
) -> CitationValidationResponse:
    return await service.validate_citation(corpus_id=corpus_id, citation=payload)


@router.post("/corpora/{corpus_id}/search", response_model=SearchResponse)
async def search_blocks(
    corpus_id: UUID, payload: SearchRequest, service: Service
) -> SearchResponse:
    matches = await service.search(corpus_id=corpus_id, request=payload)
    return SearchResponse(
        results=[
            SearchResult(
                block=SourceBlockResponse.model_validate(match.block),
                score=match.score,
            )
            for match in matches
        ]
    )

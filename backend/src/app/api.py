from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status

from app.examine_service import ExamineService, stage_event_response
from app.parsers import SourceFormat
from app.schemas import (
    AnalysisRunResponse,
    CitationRequest,
    CitationValidationResponse,
    ContradictionResponse,
    CorpusCreate,
    CorpusResponse,
    ExaminationRunResponse,
    ExaminationStageEventResponse,
    ExaminationSummaryResponse,
    FactResponse,
    FindingResponse,
    IngestionResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SourceBlockResponse,
    SourceResponse,
    SourceSummaryResponse,
    SourceVersionResponse,
    StageEventResponse,
    UnderstandingResponse,
)
from app.services import Phase02Service
from app.understand_service import UnderstandService

router = APIRouter()


def get_phase02_service(request: Request) -> Phase02Service:
    return cast(Phase02Service, request.app.state.phase02_service)


def get_understand_service(request: Request) -> UnderstandService:
    return cast(UnderstandService, request.app.state.understand_service)


def get_examine_service(request: Request) -> ExamineService:
    return cast(ExamineService, request.app.state.examine_service)


Service = Annotated[Phase02Service, Depends(get_phase02_service)]
Understand = Annotated[UnderstandService, Depends(get_understand_service)]
Examine = Annotated[ExamineService, Depends(get_examine_service)]


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


@router.post(
    "/corpora/{corpus_id}/analysis-runs",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_analysis_run(corpus_id: UUID, understand: Understand) -> AnalysisRunResponse:
    return AnalysisRunResponse.model_validate(await understand.create_run(corpus_id))


@router.get(
    "/corpora/{corpus_id}/analysis-runs/{run_id}",
    response_model=AnalysisRunResponse,
)
async def get_analysis_run(
    corpus_id: UUID, run_id: UUID, understand: Understand
) -> AnalysisRunResponse:
    return AnalysisRunResponse.model_validate(await understand.get_run(corpus_id, run_id))


@router.get(
    "/corpora/{corpus_id}/analysis-runs/{run_id}/facts",
    response_model=list[FactResponse],
)
async def get_analysis_facts(
    corpus_id: UUID, run_id: UUID, understand: Understand
) -> list[FactResponse]:
    return [
        FactResponse.model_validate(fact) for fact in await understand.list_facts(corpus_id, run_id)
    ]


@router.get(
    "/corpora/{corpus_id}/analysis-runs/{run_id}/contradictions",
    response_model=list[ContradictionResponse],
)
async def get_analysis_contradictions(
    corpus_id: UUID, run_id: UUID, understand: Understand
) -> list[ContradictionResponse]:
    return await understand.list_contradiction_responses(corpus_id, run_id)


@router.get(
    "/corpora/{corpus_id}/analysis-runs/{run_id}/understanding",
    response_model=UnderstandingResponse,
)
async def get_understanding(
    corpus_id: UUID, run_id: UUID, understand: Understand
) -> UnderstandingResponse:
    return await understand.get_understanding(corpus_id, run_id)


@router.get(
    "/corpora/{corpus_id}/analysis-runs/{run_id}/stage-events",
    response_model=list[StageEventResponse],
)
async def get_analysis_stage_events(
    corpus_id: UUID, run_id: UUID, understand: Understand
) -> list[StageEventResponse]:
    return [
        StageEventResponse.model_validate(event)
        for event in await understand.list_stage_events(corpus_id, run_id)
    ]


@router.post(
    "/corpora/{corpus_id}/analysis-runs/{analysis_run_id}/examination-runs",
    response_model=ExaminationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_examination_run(
    corpus_id: UUID, analysis_run_id: UUID, examine: Examine
) -> ExaminationRunResponse:
    return ExaminationRunResponse.model_validate(
        await examine.create_run(corpus_id, analysis_run_id)
    )


@router.get(
    "/corpora/{corpus_id}/examination-runs/{examination_run_id}",
    response_model=ExaminationRunResponse,
)
async def get_examination_run(
    corpus_id: UUID, examination_run_id: UUID, examine: Examine
) -> ExaminationRunResponse:
    return ExaminationRunResponse.model_validate(
        await examine.get_run(corpus_id, examination_run_id)
    )


@router.get(
    "/corpora/{corpus_id}/examination-runs/{examination_run_id}/findings",
    response_model=list[FindingResponse],
)
async def get_examination_findings(
    corpus_id: UUID, examination_run_id: UUID, examine: Examine
) -> list[FindingResponse]:
    return await examine.list_finding_responses(corpus_id, examination_run_id)


@router.get(
    "/corpora/{corpus_id}/examination-runs/{examination_run_id}/summary",
    response_model=ExaminationSummaryResponse,
)
async def get_examination_summary(
    corpus_id: UUID, examination_run_id: UUID, examine: Examine
) -> ExaminationSummaryResponse:
    return await examine.get_summary(corpus_id, examination_run_id)


@router.get(
    "/corpora/{corpus_id}/examination-runs/{examination_run_id}/stage-events",
    response_model=list[ExaminationStageEventResponse],
)
async def get_examination_stage_events(
    corpus_id: UUID, examination_run_id: UUID, examine: Examine
) -> list[ExaminationStageEventResponse]:
    return [
        stage_event_response(event)
        for event in await examine.list_stage_events(corpus_id, examination_run_id)
    ]

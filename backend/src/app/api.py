from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status

from app.errors import ConflictError, ValidationError
from app.examine_service import ExamineService, stage_event_response
from app.incremental_service import IncrementalService, json_object, json_object_list
from app.parsers import SourceFormat
from app.review_service import ReviewService, session_response
from app.schemas import (
    AnalysisRunResponse,
    CitationRequest,
    CitationValidationResponse,
    ContradictionResponse,
    CorpusCreate,
    CorpusResponse,
    CorpusRevisionCreate,
    CorpusRevisionResponse,
    ExaminationRunResponse,
    ExaminationStageEventResponse,
    ExaminationSummaryResponse,
    FactResponse,
    FindingResponse,
    IncrementalEvidenceResponse,
    IncrementalImpactResponse,
    IncrementalRunCreate,
    IncrementalRunResponse,
    IngestionResponse,
    ReviewDecisionCreate,
    ReviewDecisionResult,
    ReviewItemResponse,
    ReviewSessionResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SourceBlockResponse,
    SourceResponse,
    SourceSummaryResponse,
    SourceVersionResponse,
    StageEventResponse,
    UnderstandingResponse,
    WatcherPollEventResponse,
    WatcherPollResponse,
    WorkflowRunEventResponse,
    WorkflowRunResponse,
)
from app.services import Phase02Service
from app.understand_service import UnderstandService
from app.watcher import WatcherService
from app.workflow_service import WorkflowService

router = APIRouter()


def get_phase02_service(request: Request) -> Phase02Service:
    return cast(Phase02Service, request.app.state.phase02_service)


def get_understand_service(request: Request) -> UnderstandService:
    return cast(UnderstandService, request.app.state.understand_service)


def get_examine_service(request: Request) -> ExamineService:
    return cast(ExamineService, request.app.state.examine_service)


def get_review_service(request: Request) -> ReviewService:
    return cast(ReviewService, request.app.state.review_service)


def get_workflow_service(request: Request) -> WorkflowService:
    return cast(WorkflowService, request.app.state.workflow_service)


def get_incremental_service(request: Request) -> IncrementalService:
    return cast(IncrementalService, request.app.state.incremental_service)


def get_watcher_service(request: Request) -> WatcherService:
    watcher = getattr(request.app.state, "watcher_service", None)
    if watcher is None:
        raise ValidationError(
            "watcher_not_configured",
            "No watch inbox is configured for this process.",
            "Set WATCH_INPUT_PATH to a mounted inbox directory.",
        )
    return cast(WatcherService, watcher)


Service = Annotated[Phase02Service, Depends(get_phase02_service)]
Understand = Annotated[UnderstandService, Depends(get_understand_service)]
Examine = Annotated[ExamineService, Depends(get_examine_service)]
Review = Annotated[ReviewService, Depends(get_review_service)]
Workflow = Annotated[WorkflowService, Depends(get_workflow_service)]
Incremental = Annotated[IncrementalService, Depends(get_incremental_service)]
Watcher = Annotated[WatcherService, Depends(get_watcher_service)]


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


@router.post(
    "/corpora/{corpus_id}/examination-runs/{examination_run_id}/review-sessions",
    response_model=ReviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_session(
    corpus_id: UUID,
    examination_run_id: UUID,
    response: Response,
    review: Review,
) -> ReviewSessionResponse:
    session, created = await review.create_session(corpus_id, examination_run_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return session_response(session)


@router.get(
    "/corpora/{corpus_id}/review-sessions/{review_session_id}",
    response_model=ReviewSessionResponse,
)
async def get_review_session(
    corpus_id: UUID, review_session_id: UUID, review: Review
) -> ReviewSessionResponse:
    return session_response(await review.get_session(corpus_id, review_session_id))


@router.get(
    "/corpora/{corpus_id}/review-sessions/{review_session_id}/items",
    response_model=list[ReviewItemResponse],
)
async def list_review_items(
    corpus_id: UUID, review_session_id: UUID, review: Review
) -> list[ReviewItemResponse]:
    return await review.list_items(corpus_id, review_session_id)


@router.get(
    "/corpora/{corpus_id}/review-sessions/{review_session_id}/items/{item_id}",
    response_model=ReviewItemResponse,
)
async def get_review_item(
    corpus_id: UUID, review_session_id: UUID, item_id: UUID, review: Review
) -> ReviewItemResponse:
    return await review.get_item(corpus_id, review_session_id, item_id)


@router.post(
    "/corpora/{corpus_id}/review-sessions/{review_session_id}/items/{item_id}/decisions",
    response_model=ReviewDecisionResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_decision(
    corpus_id: UUID,
    review_session_id: UUID,
    item_id: UUID,
    payload: ReviewDecisionCreate,
    review: Review,
) -> ReviewDecisionResult:
    return await review.record_decision(corpus_id, review_session_id, item_id, payload)


@router.post(
    "/corpora/{corpus_id}/review-sessions/{review_session_id}/complete",
    response_model=ReviewSessionResponse,
)
async def complete_review_session(
    corpus_id: UUID, review_session_id: UUID, review: Review
) -> ReviewSessionResponse:
    return session_response(await review.complete_session(corpus_id, review_session_id))


@router.post(
    "/corpora/{corpus_id}/workflow-runs",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_run(corpus_id: UUID, workflow: Workflow) -> WorkflowRunResponse:
    return WorkflowRunResponse.model_validate(await workflow.create_run(corpus_id))


@router.get(
    "/corpora/{corpus_id}/workflow-runs/{run_id}",
    response_model=WorkflowRunResponse,
)
async def get_workflow_run(
    corpus_id: UUID, run_id: UUID, workflow: Workflow
) -> WorkflowRunResponse:
    return WorkflowRunResponse.model_validate(await workflow.get_run(corpus_id, run_id))


@router.post(
    "/corpora/{corpus_id}/workflow-runs/{run_id}/resume",
    response_model=WorkflowRunResponse,
)
async def resume_workflow_run(
    corpus_id: UUID, run_id: UUID, workflow: Workflow
) -> WorkflowRunResponse:
    return WorkflowRunResponse.model_validate(await workflow.resume_run(corpus_id, run_id))


@router.get(
    "/corpora/{corpus_id}/workflow-runs/{run_id}/events",
    response_model=list[WorkflowRunEventResponse],
)
async def list_workflow_run_events(
    corpus_id: UUID, run_id: UUID, workflow: Workflow
) -> list[WorkflowRunEventResponse]:
    return [
        WorkflowRunEventResponse.model_validate(event)
        for event in await workflow.list_events(corpus_id, run_id)
    ]


@router.post(
    "/corpora/{corpus_id}/revisions",
    response_model=CorpusRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_corpus_revision(
    corpus_id: UUID,
    payload: CorpusRevisionCreate,
    incremental: Incremental,
) -> CorpusRevisionResponse:
    revision = await incremental.create_baseline_revision(
        corpus_id,
        analysis_run_id=payload.analysis_run_id,
        examination_run_id=payload.examination_run_id,
        review_session_id=payload.review_session_id,
    )
    return CorpusRevisionResponse.model_validate(revision)


@router.get(
    "/corpora/{corpus_id}/revisions/current",
    response_model=CorpusRevisionResponse,
)
async def get_current_corpus_revision(
    corpus_id: UUID, incremental: Incremental
) -> CorpusRevisionResponse:
    return CorpusRevisionResponse.model_validate(await incremental.get_current_revision(corpus_id))


@router.post(
    "/corpora/{corpus_id}/incremental-runs",
    response_model=IncrementalRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_incremental_run(
    corpus_id: UUID,
    incremental: Incremental,
    payload: IncrementalRunCreate | None = None,
) -> IncrementalRunResponse:
    body = payload or IncrementalRunCreate()
    run = await incremental.create_run(
        corpus_id,
        baseline_revision_id=body.baseline_revision_id,
    )
    if run.status == "stale_baseline":
        raise ConflictError(
            "stale_baseline",
            run.error_detail or "The supplied baseline is not the current corpus revision.",
            run.error_action or "Reload the current corpus revision and retry.",
        )
    return IncrementalRunResponse.model_validate(run)


@router.get(
    "/corpora/{corpus_id}/incremental-runs/{run_id}",
    response_model=IncrementalRunResponse,
)
async def get_incremental_run(
    corpus_id: UUID, run_id: UUID, incremental: Incremental
) -> IncrementalRunResponse:
    return IncrementalRunResponse.model_validate(await incremental.get_run(corpus_id, run_id))


@router.get(
    "/corpora/{corpus_id}/incremental-runs/{run_id}/impact",
    response_model=IncrementalImpactResponse,
)
async def get_incremental_impact(
    corpus_id: UUID, run_id: UUID, incremental: Incremental
) -> IncrementalImpactResponse:
    return IncrementalImpactResponse(
        run_id=run_id,
        impact=await incremental.get_impact(corpus_id, run_id),
    )


@router.get(
    "/corpora/{corpus_id}/incremental-runs/{run_id}/evidence",
    response_model=IncrementalEvidenceResponse,
)
async def get_incremental_evidence(
    corpus_id: UUID, run_id: UUID, incremental: Incremental
) -> IncrementalEvidenceResponse:
    payload = await incremental.get_evidence(corpus_id, run_id)
    return IncrementalEvidenceResponse(
        run_id=run_id,
        status=str(payload["status"]),
        change_kind=str(payload["change_kind"]),
        evidence=json_object(payload["evidence"]),
        measurement=json_object(payload["measurement"]),
        artifacts=json_object_list(payload["artifacts"]),
    )


@router.post("/watcher/poll", response_model=WatcherPollResponse)
async def poll_watcher(watcher: Watcher) -> WatcherPollResponse:
    result = await watcher.poll_once()
    return WatcherPollResponse(
        examined=result.examined,
        ingested=result.ingested,
        unchanged=result.unchanged,
        triggered=result.triggered,
        failed=result.failed,
        events=[
            WatcherPollEventResponse(
                relative_path=event.relative_path,
                status=event.status,
                content_sha256=event.content_sha256,
                incremental_run_id=event.incremental_run_id,
                error_code=event.error_code,
            )
            for event in result.events
        ],
    )

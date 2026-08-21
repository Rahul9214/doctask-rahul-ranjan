"""Typed MCP result models composed from existing application schemas."""

from pydantic import BaseModel

from app.schemas import (
    CorpusResponse,
    CorpusRevisionResponse,
    ExaminationSummaryResponse,
    FindingResponse,
    IncrementalEvidenceResponse,
    ReviewItemResponse,
    ReviewSessionResponse,
    SourceSummaryResponse,
    WorkflowRunEventResponse,
    WorkflowRunResponse,
)


class CorpusListResult(BaseModel):
    corpora: list[CorpusResponse]


class SourceListResult(BaseModel):
    sources: list[SourceSummaryResponse]


class WorkflowStatusResult(BaseModel):
    run: WorkflowRunResponse
    events: list[WorkflowRunEventResponse]
    review: ReviewSessionResponse | None = None
    current_revision: CorpusRevisionResponse | None = None


class ExaminationInspectResult(BaseModel):
    summary: ExaminationSummaryResponse
    findings: list[FindingResponse]


class ReviewItemListResult(BaseModel):
    items: list[ReviewItemResponse]


class ReviewOpenResult(BaseModel):
    session: ReviewSessionResponse
    created: bool


class IncrementalEvidenceInspectResult(IncrementalEvidenceResponse):
    current_revision: CorpusRevisionResponse | None = None

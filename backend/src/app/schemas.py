from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.parsers import SUPPORTED_FORMATS, SourceFormat


class ErrorResponse(BaseModel):
    code: str
    detail: str
    action: str


class CorpusCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=200)
    declared_formats: list[SourceFormat] = Field(
        default_factory=lambda: list(SUPPORTED_FORMATS),
        min_length=1,
    )

    @field_validator("declared_formats")
    @classmethod
    def unique_formats(cls, formats: list[SourceFormat]) -> list[SourceFormat]:
        return list(dict.fromkeys(formats))


class CorpusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    domain: str
    declared_formats: list[SourceFormat]
    created_at: datetime


class SourceVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    corpus_id: UUID
    sha256: str
    media_type: str
    declared_format: SourceFormat
    original_filename: str
    storage_key: str
    byte_size: int
    parser_status: Literal["parsed"]
    created_at: datetime


class SourceSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    corpus_id: UUID
    logical_name: str
    created_at: datetime


class SourceResponse(SourceSummaryResponse):
    versions: list[SourceVersionResponse]


class SourceBlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_version_id: UUID
    corpus_id: UUID
    block_index: int
    block_type: str
    native_locator: str
    normalized_text: str
    normalized_start: int
    normalized_end: int
    metadata: dict[str, object] = Field(validation_alias="block_metadata")


class IngestionResponse(BaseModel):
    source: SourceSummaryResponse
    version: SourceVersionResponse
    duplicate: bool
    block_count: int


class CitationRequest(BaseModel):
    source_version_id: UUID
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    format: SourceFormat
    native_locator: str = Field(min_length=1, max_length=255)
    normalized_start: int = Field(ge=0)
    normalized_end: int = Field(gt=0)
    exact_quote: str = Field(min_length=1)


class CitationValidationResponse(BaseModel):
    valid: Literal[True] = True
    source_version_id: UUID
    source_block_id: UUID
    resolved_quote: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=5, ge=1, le=20)
    block_type: str | None = Field(default=None, max_length=50)
    declared_format: SourceFormat | None = None


class SearchResult(BaseModel):
    block: SourceBlockResponse
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]


class AnalysisRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    corpus_id: UUID
    status: str
    findings_status: str
    started_at: datetime | None
    completed_at: datetime | None
    model_provider_mode: str
    model_name: str
    taxonomy_version: str
    graph_version: str
    error_code: str | None
    error_detail: str | None
    created_at: datetime


class FactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    corpus_id: UUID
    category: str
    subject_key: str
    normalized_value: str
    confidence: float
    support_status: str
    rejection_reason: str | None
    citation: CitationRequest | None
    source_block_id: UUID | None
    created_at: datetime


class ContradictionResponse(BaseModel):
    id: UUID
    run_id: UUID
    corpus_id: UUID
    contradiction_type: str
    reason: str
    confidence: float
    status: str
    fact_a: FactResponse
    fact_b: FactResponse
    created_at: datetime


class StageEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    corpus_id: UUID
    stage_name: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    model_operation_count: int
    model_attempt_count: int = 0
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    cost_basis: str
    status: str
    error_code: str | None
    skip_reason: str | None = None


class BlockClassificationResponse(BaseModel):
    source_block_id: UUID
    relevant: bool
    category: str | None
    confidence: float
    rationale: str | None = None


class RejectedAssertionResponse(BaseModel):
    category: str
    subject_key: str
    normalized_value: str
    reason: str
    citation: CitationRequest | None = None


class UnderstandingResponse(BaseModel):
    run: AnalysisRunResponse
    no_findings: bool
    retrieval_mode: str | None = None
    classifications: list[BlockClassificationResponse]
    retrieved_block_ids: list[UUID]
    rejected_assertions: list[RejectedAssertionResponse]
    facts: list[FactResponse]
    contradictions: list[ContradictionResponse]
    stage_events: list[StageEventResponse]


class ExaminationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    corpus_id: UUID
    analysis_run_id: UUID
    status: str
    findings_status: str
    ruleset_version: str
    graph_version: str
    started_at: datetime | None
    completed_at: datetime | None
    pass_count: int
    fail_count: int
    warning_count: int
    unknown_count: int
    evaluated_rule_count: int
    error_code: str | None
    error_detail: str | None
    created_at: datetime


class FindingResponse(BaseModel):
    id: UUID
    examination_run_id: UUID
    corpus_id: UUID
    rule_id: str
    rule_version: str
    outcome: str
    severity: str
    title: str
    message: str
    structured_reason: dict[str, object]
    evidence_kind: str
    fact_ids: list[UUID]
    contradiction_ids: list[UUID]
    citations: list[CitationRequest]
    confidence: float
    status: str
    created_at: datetime


class ExaminationStageEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    examination_run_id: UUID
    corpus_id: UUID
    stage_name: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    model_operation_count: int
    model_attempt_count: int = 0
    rule_evaluation_count: int = 0
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    cost_basis: str
    status: str
    error_code: str | None
    skip_reason: str | None = None


class ExaminationSummaryResponse(BaseModel):
    run: ExaminationRunResponse
    no_findings: bool
    pass_count: int
    fail_count: int
    warning_count: int
    unknown_count: int
    evaluated_rule_count: int
    ruleset_version: str
    outcomes: dict[str, int]
    finding_rule_ids: list[str]


class ReviewCitation(BaseModel):
    source_version_id: UUID
    source_sha256: str
    format: SourceFormat
    native_locator: str
    normalized_start: int
    normalized_end: int
    exact_quote: str
    source_logical_name: str | None = None
    source_block_id: UUID | None = None


class ReviewDecisionCreate(BaseModel):
    action: Literal["approve", "reject", "edit"]
    edited_content: str | None = Field(default=None, max_length=8_000)
    reviewer_authored_acknowledged: bool = False
    comment: str | None = Field(default=None, max_length=2_000)
    actor: str = Field(default="reviewer", min_length=1, max_length=100)
    decision_source: Literal["api", "ui"] = "api"
    proposal_set_version: int | None = Field(default=None, ge=1)


class ReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    review_item_id: UUID
    review_session_id: UUID
    corpus_id: UUID
    action: str
    previous_status: str
    new_status: str
    original_proposed_content: dict[str, object]
    edited_content: str | None
    edited_content_is_reviewer_authored: bool
    reviewer_authored_acknowledged: bool
    comment: str | None
    actor: str
    decision_source: str
    decided_at: datetime
    created_at: datetime


class ReviewItemResponse(BaseModel):
    id: UUID
    review_session_id: UUID
    corpus_id: UUID
    examination_run_id: UUID
    finding_id: UUID
    rule_id: str
    rule_version: str
    title: str
    outcome: str
    severity: str
    message: str
    structured_reason: dict[str, object]
    evidence_kind: str
    review_required: bool
    review_status: str
    proposed_content: dict[str, object]
    edited_content: str | None
    edited_content_is_reviewer_authored: bool
    fact_ids: list[UUID]
    contradiction_ids: list[UUID]
    citations: list[ReviewCitation]
    grounded_facts: list[FactResponse]
    contradictions: list[ContradictionResponse]
    confidence: float
    created_at: datetime
    decisions: list[ReviewDecisionResponse]


class ReviewSessionResponse(BaseModel):
    id: UUID
    corpus_id: UUID
    examination_run_id: UUID
    analysis_run_id: UUID
    status: str
    proposal_set_version: int
    required_item_count: int
    optional_item_count: int
    pending_count: int
    approved_count: int
    rejected_count: int
    edited_count: int
    completion_allowed: bool
    session_creation_ms: int
    failed_complete_attempts: int
    created_at: datetime
    completed_at: datetime | None


class ReviewDecisionResult(BaseModel):
    session: ReviewSessionResponse
    item: ReviewItemResponse
    decision: ReviewDecisionResponse


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    corpus_id: UUID
    status: str
    current_stage: str
    checkpoint_thread_id: str
    analysis_run_id: UUID | None
    examination_run_id: UUID | None
    review_session_id: UUID | None
    attempt_count: int
    resume_count: int
    graph_version: str
    error_code: str | None
    error_detail: str | None
    error_action: str | None
    started_at: datetime | None
    updated_at: datetime
    completed_at: datetime | None
    created_at: datetime


class WorkflowRunEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    corpus_id: UUID
    workflow_run_id: UUID
    event_type: str
    stage_name: str | None
    payload: dict[str, object]
    duration_ms: int | None
    created_at: datetime


class CorpusRevisionCreate(BaseModel):
    analysis_run_id: UUID
    examination_run_id: UUID
    review_session_id: UUID | None = None


class CorpusRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    corpus_id: UUID
    revision_number: int
    is_current: bool
    analysis_run_id: UUID
    examination_run_id: UUID
    review_session_id: UUID | None
    source_version_set: list[dict[str, object]]
    taxonomy_version: str
    understand_graph_version: str
    prompt_config_version: str
    ruleset_version: str
    examine_graph_version: str
    created_at: datetime


class IncrementalRunCreate(BaseModel):
    baseline_revision_id: UUID | None = None


class IncrementalRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    corpus_id: UUID
    baseline_revision_id: UUID
    result_revision_id: UUID | None
    analysis_run_id: UUID | None
    examination_run_id: UUID | None
    review_session_id: UUID | None
    status: str
    change_kind: str
    error_code: str | None
    error_detail: str | None
    error_action: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class IncrementalImpactResponse(BaseModel):
    run_id: UUID
    impact: dict[str, object]


class IncrementalEvidenceResponse(BaseModel):
    run_id: UUID
    status: str
    change_kind: str
    evidence: dict[str, object]
    measurement: dict[str, object]
    artifacts: list[dict[str, object]]


class WatcherPollEventResponse(BaseModel):
    relative_path: str
    status: str
    content_sha256: str | None
    incremental_run_id: UUID | None
    error_code: str | None


class WatcherPollResponse(BaseModel):
    examined: int
    ingested: int
    unchanged: int
    triggered: int
    failed: int
    events: list[WatcherPollEventResponse]

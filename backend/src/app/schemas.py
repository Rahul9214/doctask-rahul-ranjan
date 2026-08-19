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

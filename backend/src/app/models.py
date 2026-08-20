from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIMENSIONS = 64


class Base(DeclarativeBase):
    pass


class Corpus(Base):
    __tablename__ = "corpora"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(200))
    declared_formats: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("id", "corpus_id", name="uq_sources_id_corpus"),
        UniqueConstraint("corpus_id", "logical_name", name="uq_sources_corpus_logical_name"),
        Index("ix_sources_corpus_id", "corpus_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    corpus_id: Mapped[UUID] = mapped_column(
        ForeignKey("corpora.id", ondelete="RESTRICT"), nullable=False
    )
    logical_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SourceVersion(Base):
    __tablename__ = "source_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "corpus_id"],
            ["sources.id", "sources.corpus_id"],
            name="fk_source_versions_source_corpus",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "corpus_id", name="uq_source_versions_id_corpus"),
        UniqueConstraint("source_id", "sha256", name="uq_source_versions_source_sha256"),
        UniqueConstraint("storage_key", name="uq_source_versions_storage_key"),
        CheckConstraint(
            "declared_format IN ('pdf', 'docx', 'markdown', 'txt')",
            name="ck_source_versions_declared_format",
        ),
        CheckConstraint("byte_size >= 0", name="ck_source_versions_byte_size"),
        CheckConstraint("parser_status = 'parsed'", name="ck_source_versions_parser_status"),
        Index("ix_source_versions_corpus_id", "corpus_id"),
        Index("ix_source_versions_source_id", "source_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(100))
    declared_format: Mapped[str] = mapped_column(String(20))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    parser_status: Mapped[str] = mapped_column(String(20), default="parsed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SourceBlock(Base):
    __tablename__ = "source_blocks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_version_id", "corpus_id"],
            ["source_versions.id", "source_versions.corpus_id"],
            name="fk_source_blocks_version_corpus",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("source_version_id", "block_index", name="uq_source_blocks_version_index"),
        UniqueConstraint(
            "source_version_id", "native_locator", name="uq_source_blocks_version_locator"
        ),
        UniqueConstraint("id", "corpus_id", name="uq_source_blocks_id_corpus"),
        CheckConstraint("block_index >= 0", name="ck_source_blocks_block_index"),
        CheckConstraint("normalized_start = 0", name="ck_source_blocks_start"),
        CheckConstraint(
            "normalized_end = char_length(normalized_text)",
            name="ck_source_blocks_end",
        ),
        Index("ix_source_blocks_corpus_id", "corpus_id"),
        Index("ix_source_blocks_version_id", "source_version_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_version_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    block_index: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(50))
    native_locator: Mapped[str] = mapped_column(String(255))
    normalized_text: Mapped[str] = mapped_column(Text)
    normalized_start: Mapped[int] = mapped_column(Integer, default=0)
    normalized_end: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS))
    block_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint("id", "corpus_id", name="uq_analysis_runs_id_corpus"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_analysis_runs_status",
        ),
        CheckConstraint(
            "model_provider_mode IN ('deterministic', 'openai')",
            name="ck_analysis_runs_model_mode",
        ),
        CheckConstraint(
            "findings_status IN ('pending', 'populated', 'no_findings', 'failed')",
            name="ck_analysis_runs_findings_status",
        ),
        Index("ix_analysis_runs_corpus_id", "corpus_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    corpus_id: Mapped[UUID] = mapped_column(
        ForeignKey("corpora.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    findings_status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_provider_mode: Mapped[str] = mapped_column(String(20))
    model_name: Mapped[str] = mapped_column(String(100))
    taxonomy_version: Mapped[str] = mapped_column(String(100))
    graph_version: Mapped[str] = mapped_column(String(100))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_facts_run_corpus",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_block_id", "corpus_id"],
            ["source_blocks.id", "source_blocks.corpus_id"],
            name="fk_facts_source_block_corpus",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "corpus_id", name="uq_facts_id_corpus"),
        UniqueConstraint("id", "run_id", "corpus_id", name="uq_facts_id_run_corpus"),
        CheckConstraint(
            "support_status IN ('supported', 'unknown', 'insufficient_evidence', 'rejected')",
            name="ck_facts_support_status",
        ),
        CheckConstraint(
            "support_status <> 'supported' OR "
            "(citation IS NOT NULL AND source_block_id IS NOT NULL)",
            name="ck_facts_supported_requires_provenance",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_facts_confidence"),
        Index("ix_facts_corpus_id", "corpus_id"),
        Index("ix_facts_run_id", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(String(50))
    subject_key: Mapped[str] = mapped_column(String(200))
    normalized_value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    support_status: Mapped[str] = mapped_column(String(40))
    rejection_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    citation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_block_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Contradiction(Base):
    __tablename__ = "contradictions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_contradictions_run_corpus",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["fact_a_id", "run_id", "corpus_id"],
            ["facts.id", "facts.run_id", "facts.corpus_id"],
            name="fk_contradictions_fact_a_run_corpus",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["fact_b_id", "run_id", "corpus_id"],
            ["facts.id", "facts.run_id", "facts.corpus_id"],
            name="fk_contradictions_fact_b_run_corpus",
            ondelete="RESTRICT",
        ),
        CheckConstraint("fact_a_id <> fact_b_id", name="ck_contradictions_distinct_facts"),
        CheckConstraint("fact_a_id < fact_b_id", name="ck_contradictions_canonical_pair"),
        UniqueConstraint("run_id", "fact_a_id", "fact_b_id", name="uq_contradictions_run_pair"),
        UniqueConstraint("id", "run_id", "corpus_id", name="uq_contradictions_id_run_corpus"),
        CheckConstraint(
            "contradiction_type IN ("
            "'conflicting_dates', 'conflicting_owners', 'conflicting_status', 'conflicting_risk'"
            ")",
            name="ck_contradictions_type",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_contradictions_confidence"),
        Index("ix_contradictions_corpus_id", "corpus_id"),
        Index("ix_contradictions_run_id", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    fact_a_id: Mapped[UUID] = mapped_column(nullable=False)
    fact_b_id: Mapped[UUID] = mapped_column(nullable=False)
    contradiction_type: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StageEvent(Base):
    __tablename__ = "stage_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_stage_events_run_corpus",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('started', 'completed', 'failed', 'skipped')",
            name="ck_stage_events_status",
        ),
        CheckConstraint("model_operation_count >= 0", name="ck_stage_events_operations"),
        CheckConstraint("model_attempt_count >= 0", name="ck_stage_events_attempts"),
        Index("ix_stage_events_corpus_id", "corpus_id"),
        Index("ix_stage_events_run_id", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    stage_name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_operation_count: Mapped[int] = mapped_column(Integer, default=0)
    model_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    cost_basis: Mapped[str] = mapped_column(String(100), default="zero_deterministic")
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExaminationRun(Base):
    __tablename__ = "examination_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_examination_runs_analysis_run_corpus",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "corpus_id", name="uq_examination_runs_id_corpus"),
        UniqueConstraint(
            "id",
            "corpus_id",
            "analysis_run_id",
            name="uq_examination_runs_id_corpus_analysis",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_examination_runs_status",
        ),
        CheckConstraint(
            "findings_status IN ('pending', 'populated', 'no_findings', 'failed')",
            name="ck_examination_runs_findings_status",
        ),
        CheckConstraint("pass_count >= 0", name="ck_examination_runs_pass_count"),
        CheckConstraint("fail_count >= 0", name="ck_examination_runs_fail_count"),
        CheckConstraint("warning_count >= 0", name="ck_examination_runs_warning_count"),
        CheckConstraint("unknown_count >= 0", name="ck_examination_runs_unknown_count"),
        CheckConstraint(
            "evaluated_rule_count >= 0",
            name="ck_examination_runs_evaluated_rule_count",
        ),
        Index("ix_examination_runs_corpus_id", "corpus_id"),
        Index("ix_examination_runs_analysis_run_id", "analysis_run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    corpus_id: Mapped[UUID] = mapped_column(
        ForeignKey("corpora.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_run_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    findings_status: Mapped[str] = mapped_column(String(20), default="pending")
    ruleset_version: Mapped[str] = mapped_column(String(100))
    graph_version: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    unknown_count: Mapped[int] = mapped_column(Integer, default=0)
    evaluated_rule_count: Mapped[int] = mapped_column(Integer, default=0)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "examination_runs.id",
                "examination_runs.corpus_id",
                "examination_runs.analysis_run_id",
            ],
            name="fk_findings_examination_run_corpus_analysis",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "corpus_id", name="uq_findings_id_corpus"),
        UniqueConstraint("id", "evidence_kind", name="uq_findings_id_evidence_kind"),
        UniqueConstraint(
            "id",
            "examination_run_id",
            "corpus_id",
            "analysis_run_id",
            name="uq_findings_id_run_corpus_analysis",
        ),
        UniqueConstraint("examination_run_id", "rule_id", name="uq_findings_run_rule"),
        CheckConstraint(
            "outcome IN ('pass', 'fail', 'warning', 'unknown')",
            name="ck_findings_outcome",
        ),
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high')",
            name="ck_findings_severity",
        ),
        CheckConstraint(
            "evidence_kind IN ('none', 'grounded_facts', 'process_attestation')",
            name="ck_findings_evidence_kind",
        ),
        CheckConstraint(
            "(outcome = 'unknown' AND evidence_kind = 'none') OR "
            "(outcome = 'pass' AND evidence_kind IN ('grounded_facts', 'process_attestation')) OR "
            "(outcome IN ('fail', 'warning') AND evidence_kind = 'grounded_facts')",
            name="ck_findings_outcome_evidence_kind",
        ),
        CheckConstraint("char_length(btrim(rule_id)) > 0", name="ck_findings_rule_id"),
        CheckConstraint("char_length(btrim(rule_version)) > 0", name="ck_findings_rule_version"),
        CheckConstraint(
            "jsonb_typeof(structured_reason) = 'object'",
            name="ck_findings_reason_object",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_findings_confidence"),
        Index("ix_findings_corpus_id", "corpus_id"),
        Index("ix_findings_examination_run_id", "examination_run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    examination_run_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100))
    rule_version: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    structured_reason: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_kind: Mapped[str] = mapped_column(String(40), default="none")
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="recorded")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fact_evidence: Mapped[list["FindingFactEvidence"]] = relationship(
        primaryjoin="Finding.id == foreign(FindingFactEvidence.finding_id)",
        viewonly=True,
        lazy="raise",
    )
    contradiction_evidence: Mapped[list["FindingContradictionEvidence"]] = relationship(
        primaryjoin="Finding.id == foreign(FindingContradictionEvidence.finding_id)",
        viewonly=True,
        lazy="raise",
    )

    @property
    def fact_ids(self) -> list[UUID]:
        return [item.fact_id for item in self.fact_evidence]

    @property
    def contradiction_ids(self) -> list[UUID]:
        return [item.contradiction_id for item in self.contradiction_evidence]


class FindingFactEvidence(Base):
    __tablename__ = "finding_fact_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["finding_id", "examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "findings.id",
                "findings.examination_run_id",
                "findings.corpus_id",
                "findings.analysis_run_id",
            ],
            name="fk_finding_fact_evidence_finding_run_corpus_analysis",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["finding_id", "evidence_kind"],
            ["findings.id", "findings.evidence_kind"],
            name="fk_finding_fact_evidence_finding_kind",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["fact_id", "analysis_run_id", "corpus_id"],
            ["facts.id", "facts.run_id", "facts.corpus_id"],
            name="fk_finding_fact_evidence_fact_run_corpus",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "evidence_kind = 'grounded_facts'",
            name="ck_finding_fact_evidence_kind",
        ),
        UniqueConstraint("finding_id", "fact_id", name="uq_finding_fact_evidence_finding_fact"),
        Index("ix_finding_fact_evidence_finding_id", "finding_id"),
        Index("ix_finding_fact_evidence_fact_id", "fact_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    finding_id: Mapped[UUID] = mapped_column(nullable=False)
    examination_run_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(nullable=False)
    fact_id: Mapped[UUID] = mapped_column(nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(40), default="grounded_facts")


class FindingContradictionEvidence(Base):
    __tablename__ = "finding_contradiction_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["finding_id", "examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "findings.id",
                "findings.examination_run_id",
                "findings.corpus_id",
                "findings.analysis_run_id",
            ],
            name="fk_finding_contradiction_evidence_finding_run_corpus_analysis",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["finding_id", "evidence_kind"],
            ["findings.id", "findings.evidence_kind"],
            name="fk_finding_contradiction_evidence_finding_kind",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["contradiction_id", "analysis_run_id", "corpus_id"],
            ["contradictions.id", "contradictions.run_id", "contradictions.corpus_id"],
            name="fk_finding_contradiction_evidence_contradiction_run_corpus",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "evidence_kind = 'grounded_facts'",
            name="ck_finding_contradiction_evidence_kind",
        ),
        UniqueConstraint(
            "finding_id",
            "contradiction_id",
            name="uq_finding_contradiction_evidence_finding_contradiction",
        ),
        Index("ix_finding_contradiction_evidence_finding_id", "finding_id"),
        Index("ix_finding_contradiction_evidence_contradiction_id", "contradiction_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    finding_id: Mapped[UUID] = mapped_column(nullable=False)
    examination_run_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(nullable=False)
    contradiction_id: Mapped[UUID] = mapped_column(nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(40), default="grounded_facts")


class ExaminationStageEvent(Base):
    __tablename__ = "examination_stage_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["examination_run_id", "corpus_id"],
            ["examination_runs.id", "examination_runs.corpus_id"],
            name="fk_examination_stage_events_run_corpus",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('started', 'completed', 'failed', 'skipped')",
            name="ck_examination_stage_events_status",
        ),
        CheckConstraint(
            "model_operation_count >= 0",
            name="ck_examination_stage_events_operations",
        ),
        CheckConstraint(
            "model_attempt_count >= 0",
            name="ck_examination_stage_events_attempts",
        ),
        CheckConstraint(
            "rule_evaluation_count >= 0",
            name="ck_examination_stage_events_rule_evaluations",
        ),
        Index("ix_examination_stage_events_corpus_id", "corpus_id"),
        Index("ix_examination_stage_events_run_id", "examination_run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    examination_run_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    stage_name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_operation_count: Mapped[int] = mapped_column(Integer, default=0)
    model_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_evaluation_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    cost_basis: Mapped[str] = mapped_column(String(100), default="zero_deterministic")
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewSession(Base):
    __tablename__ = "review_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "examination_runs.id",
                "examination_runs.corpus_id",
                "examination_runs.analysis_run_id",
            ],
            name="fk_review_sessions_examination_run_corpus_analysis",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "corpus_id", name="uq_review_sessions_id_corpus"),
        UniqueConstraint(
            "id",
            "corpus_id",
            "examination_run_id",
            name="uq_review_sessions_id_corpus_examination",
        ),
        UniqueConstraint(
            "id",
            "corpus_id",
            "examination_run_id",
            "analysis_run_id",
            name="uq_review_sessions_id_corpus_examination_analysis",
        ),
        UniqueConstraint(
            "corpus_id",
            "examination_run_id",
            name="uq_review_sessions_corpus_examination",
        ),
        CheckConstraint(
            "status IN ('waiting_for_review', 'completed')",
            name="ck_review_sessions_status",
        ),
        CheckConstraint(
            "(status = 'waiting_for_review' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name="ck_review_sessions_completion_timestamp",
        ),
        CheckConstraint("proposal_set_version >= 1", name="ck_review_sessions_proposal_version"),
        CheckConstraint("required_item_count >= 0", name="ck_review_sessions_required_count"),
        CheckConstraint("optional_item_count >= 0", name="ck_review_sessions_optional_count"),
        CheckConstraint("pending_count >= 0", name="ck_review_sessions_pending_count"),
        CheckConstraint("approved_count >= 0", name="ck_review_sessions_approved_count"),
        CheckConstraint("rejected_count >= 0", name="ck_review_sessions_rejected_count"),
        CheckConstraint("edited_count >= 0", name="ck_review_sessions_edited_count"),
        CheckConstraint("session_creation_ms >= 0", name="ck_review_sessions_creation_ms"),
        CheckConstraint(
            "failed_complete_attempts >= 0",
            name="ck_review_sessions_failed_complete_attempts",
        ),
        Index("ix_review_sessions_corpus_id", "corpus_id"),
        Index("ix_review_sessions_examination_run_id", "examination_run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    corpus_id: Mapped[UUID] = mapped_column(
        ForeignKey("corpora.id", ondelete="RESTRICT"), nullable=False
    )
    examination_run_id: Mapped[UUID] = mapped_column(nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="waiting_for_review")
    proposal_set_version: Mapped[int] = mapped_column(Integer, default=1)
    required_item_count: Mapped[int] = mapped_column(Integer, default=0)
    optional_item_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    approved_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    edited_count: Mapped[int] = mapped_column(Integer, default=0)
    session_creation_ms: Mapped[int] = mapped_column(Integer, default=0)
    failed_complete_attempts: Mapped[int] = mapped_column(Integer, default=0)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_session_id", "corpus_id", "examination_run_id", "analysis_run_id"],
            [
                "review_sessions.id",
                "review_sessions.corpus_id",
                "review_sessions.examination_run_id",
                "review_sessions.analysis_run_id",
            ],
            name="fk_review_items_session_corpus_examination_analysis",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["finding_id", "examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "findings.id",
                "findings.examination_run_id",
                "findings.corpus_id",
                "findings.analysis_run_id",
            ],
            name="fk_review_items_finding_run_corpus_analysis",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "corpus_id", name="uq_review_items_id_corpus"),
        UniqueConstraint(
            "id",
            "review_session_id",
            "corpus_id",
            name="uq_review_items_id_session_corpus",
        ),
        UniqueConstraint(
            "review_session_id",
            "finding_id",
            name="uq_review_items_session_finding",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected', 'edited')",
            name="ck_review_items_review_status",
        ),
        CheckConstraint(
            "jsonb_typeof(proposed_content) = 'object'",
            name="ck_review_items_proposed_object",
        ),
        CheckConstraint("char_length(btrim(rule_id)) > 0", name="ck_review_items_rule_id"),
        CheckConstraint(
            "(current_edited_content IS NULL AND "
            "edited_content_is_reviewer_authored IS FALSE) OR "
            "(current_edited_content IS NOT NULL AND "
            "char_length(btrim(current_edited_content)) > 0 AND "
            "edited_content_is_reviewer_authored IS TRUE)",
            name="ck_review_items_edited_content",
        ),
        Index("ix_review_items_corpus_id", "corpus_id"),
        Index("ix_review_items_review_session_id", "review_session_id"),
        Index("ix_review_items_finding_id", "finding_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_session_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    examination_run_id: Mapped[UUID] = mapped_column(nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(nullable=False)
    finding_id: Mapped[UUID] = mapped_column(nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    proposed_content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    current_edited_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_content_is_reviewer_authored: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_item_id", "review_session_id", "corpus_id"],
            ["review_items.id", "review_items.review_session_id", "review_items.corpus_id"],
            name="fk_review_decisions_item_session_corpus",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["review_session_id", "corpus_id"],
            ["review_sessions.id", "review_sessions.corpus_id"],
            name="fk_review_decisions_session_corpus",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "corpus_id", name="uq_review_decisions_id_corpus"),
        CheckConstraint(
            "action IN ('approve', 'reject', 'edit')",
            name="ck_review_decisions_action",
        ),
        CheckConstraint(
            "previous_status IN ('pending', 'approved', 'rejected', 'edited')",
            name="ck_review_decisions_previous_status",
        ),
        CheckConstraint(
            "new_status IN ('pending', 'approved', 'rejected', 'edited')",
            name="ck_review_decisions_new_status",
        ),
        CheckConstraint(
            "(action = 'approve' AND new_status = 'approved') OR "
            "(action = 'reject' AND new_status = 'rejected') OR "
            "(action = 'edit' AND new_status = 'edited')",
            name="ck_review_decisions_action_status",
        ),
        CheckConstraint(
            "(action <> 'edit' AND edited_content IS NULL AND "
            "edited_content_is_reviewer_authored IS FALSE AND "
            "reviewer_authored_acknowledged IS FALSE) OR "
            "(action = 'edit' AND edited_content IS NOT NULL AND "
            "char_length(btrim(edited_content)) > 0 AND "
            "edited_content_is_reviewer_authored IS TRUE AND "
            "reviewer_authored_acknowledged IS TRUE)",
            name="ck_review_decisions_edit_content",
        ),
        CheckConstraint(
            "decision_source IN ('api', 'ui')",
            name="ck_review_decisions_source",
        ),
        CheckConstraint("char_length(btrim(actor)) > 0", name="ck_review_decisions_actor"),
        Index("ix_review_decisions_corpus_id", "corpus_id"),
        Index("ix_review_decisions_review_item_id", "review_item_id"),
        Index("ix_review_decisions_review_session_id", "review_session_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_item_id: Mapped[UUID] = mapped_column(nullable=False)
    review_session_id: Mapped[UUID] = mapped_column(nullable=False)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(20))
    previous_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    original_proposed_content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    edited_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_content_is_reviewer_authored: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_authored_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(100), default="reviewer")
    decision_source: Mapped[str] = mapped_column(String(20), default="api")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("id", "corpus_id", name="uq_workflow_runs_id_corpus"),
        UniqueConstraint("checkpoint_thread_id", name="uq_workflow_runs_checkpoint_thread_id"),
        ForeignKeyConstraint(
            ["analysis_run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_workflow_runs_analysis_run_corpus",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["examination_run_id", "corpus_id"],
            ["examination_runs.id", "examination_runs.corpus_id"],
            name="fk_workflow_runs_examination_run_corpus",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["review_session_id", "corpus_id"],
            ["review_sessions.id", "review_sessions.corpus_id"],
            name="fk_workflow_runs_review_session_corpus",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'waiting_for_review', 'failed', 'completed')",
            name="ck_workflow_runs_status",
        ),
        CheckConstraint(
            "current_stage IN ("
            "'pending', 'understand', 'examine', 'open_review', "
            "'wait_for_review', 'finalize', 'completed'"
            ")",
            name="ck_workflow_runs_current_stage",
        ),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL)",
            name="ck_workflow_runs_completion_timestamp",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_workflow_runs_attempt_count"),
        CheckConstraint("resume_count >= 0", name="ck_workflow_runs_resume_count"),
        CheckConstraint(
            "char_length(btrim(checkpoint_thread_id)) > 0",
            name="ck_workflow_runs_checkpoint_thread_id",
        ),
        Index("ix_workflow_runs_corpus_id", "corpus_id"),
        Index("ix_workflow_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    corpus_id: Mapped[UUID] = mapped_column(
        ForeignKey("corpora.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default="pending")
    current_stage: Mapped[str] = mapped_column(String(40), default="pending")
    checkpoint_thread_id: Mapped[str] = mapped_column(String(64))
    analysis_run_id: Mapped[UUID | None] = mapped_column(nullable=True)
    examination_run_id: Mapped[UUID | None] = mapped_column(nullable=True)
    review_session_id: Mapped[UUID | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    resume_count: Mapped[int] = mapped_column(Integer, default=0)
    graph_version: Mapped[str] = mapped_column(String(100))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DurableOperation(Base):
    __tablename__ = "durable_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "corpus_id"],
            ["workflow_runs.id", "workflow_runs.corpus_id"],
            name="fk_durable_operations_run_corpus",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("operation_key", name="uq_durable_operations_operation_key"),
        UniqueConstraint("id", "corpus_id", name="uq_durable_operations_id_corpus"),
        CheckConstraint(
            "status IN ('intended', 'in_flight', 'completed', 'failed', 'ambiguous')",
            name="ck_durable_operations_status",
        ),
        CheckConstraint(
            "logical_operation_count IN (0, 1)",
            name="ck_durable_operations_logical_count",
        ),
        CheckConstraint(
            "provider_attempt_count >= 0",
            name="ck_durable_operations_attempt_count",
        ),
        CheckConstraint(
            "status <> 'intended' OR (logical_operation_count = 0 AND provider_attempt_count = 0)",
            name="ck_durable_operations_intended",
        ),
        CheckConstraint(
            "status <> 'in_flight' OR "
            "(logical_operation_count = 0 AND provider_attempt_count >= 1)",
            name="ck_durable_operations_in_flight",
        ),
        CheckConstraint(
            "status <> 'completed' OR ("
            "result_hash IS NOT NULL AND char_length(btrim(result_hash)) = 64 "
            "AND logical_operation_count = 1 AND provider_attempt_count >= 1"
            ")",
            name="ck_durable_operations_completed",
        ),
        CheckConstraint(
            "status <> 'failed' OR logical_operation_count = 0",
            name="ck_durable_operations_failed",
        ),
        CheckConstraint(
            "status <> 'ambiguous' OR "
            "(logical_operation_count = 0 AND provider_attempt_count >= 1)",
            name="ck_durable_operations_ambiguous",
        ),
        CheckConstraint(
            "char_length(btrim(operation_key)) = 64",
            name="ck_durable_operations_operation_key",
        ),
        Index("ix_durable_operations_corpus_id", "corpus_id"),
        Index("ix_durable_operations_workflow_run_id", "workflow_run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    workflow_run_id: Mapped[UUID] = mapped_column(nullable=False)
    operation_key: Mapped[str] = mapped_column(String(64))
    operation_type: Mapped[str] = mapped_column(String(50))
    stage: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="intended")
    request_hash: Mapped[str] = mapped_column(String(64))
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    logical_operation_count: Mapped[int] = mapped_column(Integer, default=0)
    provider_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    provider_idempotency_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_input_version: Mapped[str] = mapped_column(String(64))
    model_provider: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkflowRunEvent(Base):
    __tablename__ = "workflow_run_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "corpus_id"],
            ["workflow_runs.id", "workflow_runs.corpus_id"],
            name="fk_workflow_run_events_run_corpus",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "corpus_id", name="uq_workflow_run_events_id_corpus"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_workflow_run_events_ms"
        ),
        Index("ix_workflow_run_events_corpus_id", "corpus_id"),
        Index("ix_workflow_run_events_workflow_run_id", "workflow_run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    corpus_id: Mapped[UUID] = mapped_column(nullable=False)
    workflow_run_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(80))
    stage_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

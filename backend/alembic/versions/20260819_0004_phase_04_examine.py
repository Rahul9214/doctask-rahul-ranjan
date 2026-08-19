"""Create the Phase 04 examination run, finding, and evidence schema.

Revision ID: 20260819_0004
Revises: 20260819_0003
Create Date: 2026-08-19

This uncommitted revision may be edited in place until Phase 04 is committed.
Alembic will not reapply the same revision ID against a database already stamped
at 20260819_0004. Local databases left on the previous 0004 JSON-evidence schema
must be recovered explicitly: drop leftover Phase 04 objects, stamp 20260819_0003,
then upgrade. Do not silently destroy non-test data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260819_0004"
down_revision: str | None = "20260819_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_contradictions_id_run_corpus",
        "contradictions",
        ["id", "run_id", "corpus_id"],
    )

    op.create_table(
        "examination_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("findings_status", sa.String(length=20), nullable=False),
        sa.Column("ruleset_version", sa.String(length=100), nullable=False),
        sa.Column("graph_version", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pass_count", sa.Integer(), nullable=False),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("unknown_count", sa.Integer(), nullable=False),
        sa.Column("evaluated_rule_count", sa.Integer(), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_examination_runs_status",
        ),
        sa.CheckConstraint(
            "findings_status IN ('pending', 'populated', 'no_findings', 'failed')",
            name="ck_examination_runs_findings_status",
        ),
        sa.CheckConstraint("pass_count >= 0", name="ck_examination_runs_pass_count"),
        sa.CheckConstraint("fail_count >= 0", name="ck_examination_runs_fail_count"),
        sa.CheckConstraint("warning_count >= 0", name="ck_examination_runs_warning_count"),
        sa.CheckConstraint("unknown_count >= 0", name="ck_examination_runs_unknown_count"),
        sa.CheckConstraint(
            "evaluated_rule_count >= 0",
            name="ck_examination_runs_evaluated_rule_count",
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["analysis_run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_examination_runs_analysis_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_examination_runs_id_corpus"),
        sa.UniqueConstraint(
            "id",
            "corpus_id",
            "analysis_run_id",
            name="uq_examination_runs_id_corpus_analysis",
        ),
    )
    op.create_index("ix_examination_runs_corpus_id", "examination_runs", ["corpus_id"])
    op.create_index("ix_examination_runs_analysis_run_id", "examination_runs", ["analysis_run_id"])

    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("rule_version", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("structured_reason", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_kind", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('pass', 'fail', 'warning', 'unknown')",
            name="ck_findings_outcome",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high')",
            name="ck_findings_severity",
        ),
        sa.CheckConstraint(
            "evidence_kind IN ('none', 'grounded_facts', 'process_attestation')",
            name="ck_findings_evidence_kind",
        ),
        sa.CheckConstraint(
            "(outcome = 'unknown' AND evidence_kind = 'none') OR "
            "(outcome = 'pass' AND evidence_kind IN ('grounded_facts', 'process_attestation')) OR "
            "(outcome IN ('fail', 'warning') AND evidence_kind = 'grounded_facts')",
            name="ck_findings_outcome_evidence_kind",
        ),
        sa.CheckConstraint("char_length(btrim(rule_id)) > 0", name="ck_findings_rule_id"),
        sa.CheckConstraint("char_length(btrim(rule_version)) > 0", name="ck_findings_rule_version"),
        sa.CheckConstraint(
            "jsonb_typeof(structured_reason) = 'object'",
            name="ck_findings_reason_object",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_findings_confidence"),
        sa.ForeignKeyConstraint(
            ["examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "examination_runs.id",
                "examination_runs.corpus_id",
                "examination_runs.analysis_run_id",
            ],
            name="fk_findings_examination_run_corpus_analysis",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_findings_id_corpus"),
        sa.UniqueConstraint("id", "evidence_kind", name="uq_findings_id_evidence_kind"),
        sa.UniqueConstraint(
            "id",
            "examination_run_id",
            "corpus_id",
            "analysis_run_id",
            name="uq_findings_id_run_corpus_analysis",
        ),
        sa.UniqueConstraint("examination_run_id", "rule_id", name="uq_findings_run_rule"),
    )
    op.create_index("ix_findings_corpus_id", "findings", ["corpus_id"])
    op.create_index("ix_findings_examination_run_id", "findings", ["examination_run_id"])

    op.create_table(
        "finding_fact_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_kind", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "evidence_kind = 'grounded_facts'",
            name="ck_finding_fact_evidence_kind",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
            ["finding_id", "evidence_kind"],
            ["findings.id", "findings.evidence_kind"],
            name="fk_finding_fact_evidence_finding_kind",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fact_id", "analysis_run_id", "corpus_id"],
            ["facts.id", "facts.run_id", "facts.corpus_id"],
            name="fk_finding_fact_evidence_fact_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_id",
            "fact_id",
            name="uq_finding_fact_evidence_finding_fact",
        ),
    )
    op.create_index(
        "ix_finding_fact_evidence_finding_id",
        "finding_fact_evidence",
        ["finding_id"],
    )
    op.create_index("ix_finding_fact_evidence_fact_id", "finding_fact_evidence", ["fact_id"])

    op.create_table(
        "finding_contradiction_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("contradiction_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_kind", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "evidence_kind = 'grounded_facts'",
            name="ck_finding_contradiction_evidence_kind",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
            ["finding_id", "evidence_kind"],
            ["findings.id", "findings.evidence_kind"],
            name="fk_finding_contradiction_evidence_finding_kind",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contradiction_id", "analysis_run_id", "corpus_id"],
            ["contradictions.id", "contradictions.run_id", "contradictions.corpus_id"],
            name="fk_finding_contradiction_evidence_contradiction_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_id",
            "contradiction_id",
            name="uq_finding_contradiction_evidence_finding_contradiction",
        ),
    )
    op.create_index(
        "ix_finding_contradiction_evidence_finding_id",
        "finding_contradiction_evidence",
        ["finding_id"],
    )
    op.create_index(
        "ix_finding_contradiction_evidence_contradiction_id",
        "finding_contradiction_evidence",
        ["contradiction_id"],
    )

    op.create_table(
        "examination_stage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("stage_name", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("model_operation_count", sa.Integer(), nullable=False),
        sa.Column("model_attempt_count", sa.Integer(), nullable=False),
        sa.Column("rule_evaluation_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("cost_basis", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("skip_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed', 'skipped')",
            name="ck_examination_stage_events_status",
        ),
        sa.CheckConstraint(
            "model_operation_count >= 0",
            name="ck_examination_stage_events_operations",
        ),
        sa.CheckConstraint(
            "model_attempt_count >= 0",
            name="ck_examination_stage_events_attempts",
        ),
        sa.CheckConstraint(
            "rule_evaluation_count >= 0",
            name="ck_examination_stage_events_rule_evaluations",
        ),
        sa.ForeignKeyConstraint(
            ["examination_run_id", "corpus_id"],
            ["examination_runs.id", "examination_runs.corpus_id"],
            name="fk_examination_stage_events_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_examination_stage_events_corpus_id", "examination_stage_events", ["corpus_id"]
    )
    op.create_index(
        "ix_examination_stage_events_run_id",
        "examination_stage_events",
        ["examination_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_examination_stage_events_run_id", table_name="examination_stage_events")
    op.drop_index("ix_examination_stage_events_corpus_id", table_name="examination_stage_events")
    op.drop_table("examination_stage_events")
    op.drop_index(
        "ix_finding_contradiction_evidence_contradiction_id",
        table_name="finding_contradiction_evidence",
    )
    op.drop_index(
        "ix_finding_contradiction_evidence_finding_id",
        table_name="finding_contradiction_evidence",
    )
    op.drop_table("finding_contradiction_evidence")
    op.drop_index("ix_finding_fact_evidence_fact_id", table_name="finding_fact_evidence")
    op.drop_index("ix_finding_fact_evidence_finding_id", table_name="finding_fact_evidence")
    op.drop_table("finding_fact_evidence")
    op.drop_index("ix_findings_examination_run_id", table_name="findings")
    op.drop_index("ix_findings_corpus_id", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_examination_runs_analysis_run_id", table_name="examination_runs")
    op.drop_index("ix_examination_runs_corpus_id", table_name="examination_runs")
    op.drop_table("examination_runs")
    op.drop_constraint("uq_contradictions_id_run_corpus", "contradictions", type_="unique")

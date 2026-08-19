"""Create the Phase 03 analysis run, fact, contradiction, and stage event schema.

Revision ID: 20260819_0003
Revises: 20260819_0002
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260819_0003"
down_revision: str | None = "20260819_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("findings_status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_provider_mode", sa.String(length=20), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=100), nullable=False),
        sa.Column("graph_version", sa.String(length=100), nullable=False),
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
            "findings_status IN ('pending', 'populated', 'no_findings', 'failed')",
            name="ck_analysis_runs_findings_status",
        ),
        sa.CheckConstraint(
            "model_provider_mode IN ('deterministic', 'openai')",
            name="ck_analysis_runs_model_mode",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_analysis_runs_status",
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_analysis_runs_id_corpus"),
    )
    op.create_index("ix_analysis_runs_corpus_id", "analysis_runs", ["corpus_id"])
    op.create_unique_constraint("uq_source_blocks_id_corpus", "source_blocks", ["id", "corpus_id"])

    op.create_table(
        "facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("subject_key", sa.String(length=200), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("support_status", sa.String(length=40), nullable=False),
        sa.Column("rejection_reason", sa.String(length=100), nullable=True),
        sa.Column("citation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_block_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_facts_confidence"),
        sa.CheckConstraint(
            "support_status IN ('supported', 'unknown', 'insufficient_evidence', 'rejected')",
            name="ck_facts_support_status",
        ),
        sa.CheckConstraint(
            "support_status <> 'supported' OR "
            "(citation IS NOT NULL AND source_block_id IS NOT NULL)",
            name="ck_facts_supported_requires_provenance",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_facts_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_block_id", "corpus_id"],
            ["source_blocks.id", "source_blocks.corpus_id"],
            name="fk_facts_source_block_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_facts_id_corpus"),
        sa.UniqueConstraint("id", "run_id", "corpus_id", name="uq_facts_id_run_corpus"),
    )
    op.create_index("ix_facts_corpus_id", "facts", ["corpus_id"])
    op.create_index("ix_facts_run_id", "facts", ["run_id"])

    op.create_table(
        "contradictions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("fact_a_id", sa.Uuid(), nullable=False),
        sa.Column("fact_b_id", sa.Uuid(), nullable=False),
        sa.Column("contradiction_type", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("fact_a_id <> fact_b_id", name="ck_contradictions_distinct_facts"),
        sa.CheckConstraint("fact_a_id < fact_b_id", name="ck_contradictions_canonical_pair"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_contradictions_confidence"
        ),
        sa.CheckConstraint(
            "contradiction_type IN ("
            "'conflicting_dates', 'conflicting_owners', 'conflicting_status', 'conflicting_risk'"
            ")",
            name="ck_contradictions_type",
        ),
        sa.ForeignKeyConstraint(
            ["fact_a_id", "run_id", "corpus_id"],
            ["facts.id", "facts.run_id", "facts.corpus_id"],
            name="fk_contradictions_fact_a_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fact_b_id", "run_id", "corpus_id"],
            ["facts.id", "facts.run_id", "facts.corpus_id"],
            name="fk_contradictions_fact_b_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_contradictions_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "fact_a_id", "fact_b_id", name="uq_contradictions_run_pair"),
    )
    op.create_index("ix_contradictions_corpus_id", "contradictions", ["corpus_id"])
    op.create_index("ix_contradictions_run_id", "contradictions", ["run_id"])

    op.create_table(
        "stage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("stage_name", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("model_operation_count", sa.Integer(), nullable=False),
        sa.Column("model_attempt_count", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("model_operation_count >= 0", name="ck_stage_events_operations"),
        sa.CheckConstraint("model_attempt_count >= 0", name="ck_stage_events_attempts"),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed', 'skipped')",
            name="ck_stage_events_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_stage_events_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stage_events_corpus_id", "stage_events", ["corpus_id"])
    op.create_index("ix_stage_events_run_id", "stage_events", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_stage_events_run_id", table_name="stage_events")
    op.drop_index("ix_stage_events_corpus_id", table_name="stage_events")
    op.drop_table("stage_events")
    op.drop_index("ix_contradictions_run_id", table_name="contradictions")
    op.drop_index("ix_contradictions_corpus_id", table_name="contradictions")
    op.drop_table("contradictions")
    op.drop_index("ix_facts_run_id", table_name="facts")
    op.drop_index("ix_facts_corpus_id", table_name="facts")
    op.drop_table("facts")
    op.drop_index("ix_analysis_runs_corpus_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_constraint("uq_source_blocks_id_corpus", "source_blocks", type_="unique")

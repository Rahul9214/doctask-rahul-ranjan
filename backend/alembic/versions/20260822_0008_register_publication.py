"""Create immutable published register schema after completed human review.

Revision ID: 20260822_0008
Revises: 20260819_0007
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260822_0008"
down_revision: str | None = "20260819_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_workflow_runs_examination_chain",
        "workflow_runs",
        "examination_runs",
        ["examination_run_id", "corpus_id", "analysis_run_id"],
        ["id", "corpus_id", "analysis_run_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_workflow_runs_review_chain",
        "workflow_runs",
        "review_sessions",
        ["review_session_id", "corpus_id", "examination_run_id", "analysis_run_id"],
        ["id", "corpus_id", "examination_run_id", "analysis_run_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_corpus_revisions_examination_chain",
        "corpus_revisions",
        "examination_runs",
        ["examination_run_id", "corpus_id", "analysis_run_id"],
        ["id", "corpus_id", "analysis_run_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_corpus_revisions_review_chain",
        "corpus_revisions",
        "review_sessions",
        ["review_session_id", "corpus_id", "examination_run_id", "analysis_run_id"],
        ["id", "corpus_id", "examination_run_id", "analysis_run_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_review_items_id_session_corpus_chain_finding",
        "review_items",
        [
            "id",
            "review_session_id",
            "corpus_id",
            "examination_run_id",
            "analysis_run_id",
            "finding_id",
        ],
    )
    op.create_unique_constraint(
        "uq_workflow_runs_id_corpus_chain",
        "workflow_runs",
        [
            "id",
            "corpus_id",
            "analysis_run_id",
            "examination_run_id",
            "review_session_id",
        ],
    )
    op.create_unique_constraint(
        "uq_corpus_revisions_id_corpus_chain",
        "corpus_revisions",
        [
            "id",
            "corpus_id",
            "analysis_run_id",
            "examination_run_id",
            "review_session_id",
        ],
    )
    op.create_table(
        "published_registers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("publication_number", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("review_session_id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("corpus_revision_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("register_status", sa.String(length=40), nullable=False),
        sa.Column("version_identity", sa.String(length=120), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("publication_source", sa.String(length=20), nullable=False),
        sa.Column("applied_count", sa.Integer(), nullable=False),
        sa.Column("rejected_omitted_count", sa.Integer(), nullable=False),
        sa.Column("pending_optional_omitted_count", sa.Integer(), nullable=False),
        sa.Column("edited_count", sa.Integer(), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("publication_number >= 1", name="ck_published_registers_number"),
        sa.CheckConstraint("status = 'published'", name="ck_published_registers_status"),
        sa.CheckConstraint(
            "register_status IN ("
            "'populated', 'no_findings', 'insufficient_evidence', 'empty_after_review'"
            ")",
            name="ck_published_registers_register_status",
        ),
        sa.CheckConstraint(
            "publication_source IN ('api', 'ui')",
            name="ck_published_registers_source",
        ),
        sa.CheckConstraint("char_length(btrim(actor)) > 0", name="ck_published_registers_actor"),
        sa.CheckConstraint(
            "char_length(content_sha256) = 64",
            name="ck_published_registers_content_sha256",
        ),
        sa.CheckConstraint("applied_count >= 0", name="ck_published_registers_applied"),
        sa.CheckConstraint("rejected_omitted_count >= 0", name="ck_published_registers_rejected"),
        sa.CheckConstraint(
            "pending_optional_omitted_count >= 0",
            name="ck_published_registers_pending_optional",
        ),
        sa.CheckConstraint("edited_count >= 0", name="ck_published_registers_edited"),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            [
                "review_session_id",
                "corpus_id",
                "examination_run_id",
                "analysis_run_id",
            ],
            [
                "review_sessions.id",
                "review_sessions.corpus_id",
                "review_sessions.examination_run_id",
                "review_sessions.analysis_run_id",
            ],
            name="fk_published_registers_review_chain",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "examination_runs.id",
                "examination_runs.corpus_id",
                "examination_runs.analysis_run_id",
            ],
            name="fk_published_registers_examination_chain",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "workflow_run_id",
                "corpus_id",
                "analysis_run_id",
                "examination_run_id",
                "review_session_id",
            ],
            [
                "workflow_runs.id",
                "workflow_runs.corpus_id",
                "workflow_runs.analysis_run_id",
                "workflow_runs.examination_run_id",
                "workflow_runs.review_session_id",
            ],
            name="fk_published_registers_workflow_chain",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "corpus_revision_id",
                "corpus_id",
                "analysis_run_id",
                "examination_run_id",
                "review_session_id",
            ],
            [
                "corpus_revisions.id",
                "corpus_revisions.corpus_id",
                "corpus_revisions.analysis_run_id",
                "corpus_revisions.examination_run_id",
                "corpus_revisions.review_session_id",
            ],
            name="fk_published_registers_revision_chain",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_published_registers_id_corpus"),
        sa.UniqueConstraint(
            "id",
            "corpus_id",
            "review_session_id",
            "examination_run_id",
            "analysis_run_id",
            name="uq_published_registers_id_corpus_chain",
        ),
        sa.UniqueConstraint(
            "corpus_id",
            "review_session_id",
            name="uq_published_registers_corpus_session",
        ),
        sa.UniqueConstraint(
            "corpus_id",
            "publication_number",
            name="uq_published_registers_corpus_number",
        ),
    )
    op.create_index("ix_published_registers_corpus_id", "published_registers", ["corpus_id"])
    op.create_index(
        "uq_published_registers_current",
        "published_registers",
        ["corpus_id"],
        unique=True,
        postgresql_where=sa.text("is_current IS TRUE"),
    )

    op.create_table(
        "published_register_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("published_register_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("review_session_id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("rule_version", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("structured_reason", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_kind", sa.String(length=40), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("content_origin", sa.String(length=40), nullable=False),
        sa.Column("reviewer_authored_content", sa.Text(), nullable=True),
        sa.Column("reviewer_authored_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("value_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_status IN ('approved', 'edited')",
            name="ck_published_register_items_review_status",
        ),
        sa.CheckConstraint(
            "content_origin IN ('system_grounded', 'mixed')",
            name="ck_published_register_items_content_origin",
        ),
        sa.CheckConstraint(
            "outcome IN ('pass', 'fail', 'warning', 'unknown')",
            name="ck_published_register_items_outcome",
        ),
        sa.CheckConstraint(
            "(review_status = 'approved' AND content_origin = 'system_grounded' AND "
            "reviewer_authored_content IS NULL) OR "
            "(review_status = 'edited' AND content_origin = 'mixed' AND "
            "reviewer_authored_content IS NOT NULL AND "
            "char_length(btrim(reviewer_authored_content)) > 0 AND "
            "reviewer_authored_acknowledged IS TRUE)",
            name="ck_published_register_items_authorship",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(structured_reason) = 'object'",
            name="ck_published_register_items_reason_object",
        ),
        sa.CheckConstraint(
            "char_length(value_hash) = 64",
            name="ck_published_register_items_value_hash",
        ),
        sa.ForeignKeyConstraint(
            [
                "published_register_id",
                "corpus_id",
                "review_session_id",
                "examination_run_id",
                "analysis_run_id",
            ],
            [
                "published_registers.id",
                "published_registers.corpus_id",
                "published_registers.review_session_id",
                "published_registers.examination_run_id",
                "published_registers.analysis_run_id",
            ],
            name="fk_published_register_items_register_chain",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "review_item_id",
                "review_session_id",
                "corpus_id",
                "examination_run_id",
                "analysis_run_id",
                "finding_id",
            ],
            [
                "review_items.id",
                "review_items.review_session_id",
                "review_items.corpus_id",
                "review_items.examination_run_id",
                "review_items.analysis_run_id",
                "review_items.finding_id",
            ],
            name="fk_published_register_items_review_item_chain",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id", "examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "findings.id",
                "findings.examination_run_id",
                "findings.corpus_id",
                "findings.analysis_run_id",
            ],
            name="fk_published_register_items_finding_chain",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_published_register_items_id_corpus"),
        sa.UniqueConstraint(
            "id",
            "published_register_id",
            "corpus_id",
            name="uq_published_register_items_id_register_corpus",
        ),
        sa.UniqueConstraint(
            "id",
            "published_register_id",
            "corpus_id",
            "analysis_run_id",
            name="uq_published_register_items_id_register_corpus_analysis",
        ),
        sa.UniqueConstraint(
            "published_register_id",
            "review_item_id",
            name="uq_published_register_items_register_review_item",
        ),
        sa.UniqueConstraint(
            "published_register_id",
            "rule_id",
            name="uq_published_register_items_register_rule",
        ),
    )
    op.create_index(
        "ix_published_register_items_corpus_id",
        "published_register_items",
        ["corpus_id"],
    )
    op.create_index(
        "ix_published_register_items_register_id",
        "published_register_items",
        ["published_register_id"],
    )

    op.create_table(
        "published_register_item_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("published_item_id", sa.Uuid(), nullable=False),
        sa.Column("published_register_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["published_item_id", "published_register_id", "corpus_id", "analysis_run_id"],
            [
                "published_register_items.id",
                "published_register_items.published_register_id",
                "published_register_items.corpus_id",
                "published_register_items.analysis_run_id",
            ],
            name="fk_published_item_facts_item_register_corpus_analysis",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fact_id", "analysis_run_id", "corpus_id"],
            ["facts.id", "facts.run_id", "facts.corpus_id"],
            name="fk_published_item_facts_fact_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "published_item_id",
            "fact_id",
            name="uq_published_item_facts_item_fact",
        ),
    )
    op.create_index(
        "ix_published_item_facts_item_id",
        "published_register_item_facts",
        ["published_item_id"],
    )
    op.create_index(
        "ix_published_item_facts_fact_id",
        "published_register_item_facts",
        ["fact_id"],
    )

    op.create_table(
        "published_register_item_contradictions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("published_item_id", sa.Uuid(), nullable=False),
        sa.Column("published_register_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("contradiction_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["published_item_id", "published_register_id", "corpus_id", "analysis_run_id"],
            [
                "published_register_items.id",
                "published_register_items.published_register_id",
                "published_register_items.corpus_id",
                "published_register_items.analysis_run_id",
            ],
            name="fk_published_item_contradictions_item_register_analysis",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contradiction_id", "analysis_run_id", "corpus_id"],
            ["contradictions.id", "contradictions.run_id", "contradictions.corpus_id"],
            name="fk_published_item_contradictions_contradiction",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "published_item_id",
            "contradiction_id",
            name="uq_published_item_contradictions_item_contradiction",
        ),
    )
    op.create_index(
        "ix_published_item_contradictions_item_id",
        "published_register_item_contradictions",
        ["published_item_id"],
    )
    op.create_index(
        "ix_published_item_contradictions_contradiction_id",
        "published_register_item_contradictions",
        ["contradiction_id"],
    )

    op.create_table(
        "publication_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("published_register_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("publication_source", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'published', 'item_applied', 'item_applied_with_reviewer_edit', "
            "'item_omitted_rejected', 'item_omitted_pending_optional'"
            ")",
            name="ck_publication_events_type",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_publication_events_payload_object",
        ),
        sa.ForeignKeyConstraint(
            ["published_register_id", "corpus_id"],
            ["published_registers.id", "published_registers.corpus_id"],
            name="fk_publication_events_register_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_publication_events_corpus_id", "publication_events", ["corpus_id"])
    op.create_index(
        "ix_publication_events_register_id",
        "publication_events",
        ["published_register_id"],
    )


def _drop_constraint_if_exists(table_name: str, constraint_name: str) -> None:
    """Recover older locally-applied forms of this still-uncommitted revision."""
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'))


def downgrade() -> None:
    op.drop_index("ix_publication_events_register_id", table_name="publication_events")
    op.drop_index("ix_publication_events_corpus_id", table_name="publication_events")
    op.drop_table("publication_events")
    op.drop_index(
        "ix_published_item_contradictions_contradiction_id",
        table_name="published_register_item_contradictions",
    )
    op.drop_index(
        "ix_published_item_contradictions_item_id",
        table_name="published_register_item_contradictions",
    )
    op.drop_table("published_register_item_contradictions")
    op.drop_index("ix_published_item_facts_fact_id", table_name="published_register_item_facts")
    op.drop_index("ix_published_item_facts_item_id", table_name="published_register_item_facts")
    op.drop_table("published_register_item_facts")
    op.drop_index(
        "ix_published_register_items_register_id",
        table_name="published_register_items",
    )
    op.drop_index(
        "ix_published_register_items_corpus_id",
        table_name="published_register_items",
    )
    op.drop_table("published_register_items")
    op.drop_index("uq_published_registers_current", table_name="published_registers")
    op.drop_index("ix_published_registers_corpus_id", table_name="published_registers")
    op.drop_table("published_registers")
    _drop_constraint_if_exists("corpus_revisions", "fk_corpus_revisions_review_chain")
    _drop_constraint_if_exists("corpus_revisions", "fk_corpus_revisions_examination_chain")
    _drop_constraint_if_exists("workflow_runs", "fk_workflow_runs_review_chain")
    _drop_constraint_if_exists("workflow_runs", "fk_workflow_runs_examination_chain")
    _drop_constraint_if_exists("corpus_revisions", "uq_corpus_revisions_id_corpus_chain")
    _drop_constraint_if_exists("workflow_runs", "uq_workflow_runs_id_corpus_chain")
    _drop_constraint_if_exists("review_items", "uq_review_items_id_session_corpus_chain_finding")

"""Create the Phase 05 human-review session, item, and decision schema.

Revision ID: 20260819_0005
Revises: 20260819_0004
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260819_0005"
down_revision: str | None = "20260819_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("proposal_set_version", sa.Integer(), nullable=False),
        sa.Column("required_item_count", sa.Integer(), nullable=False),
        sa.Column("optional_item_count", sa.Integer(), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False),
        sa.Column("approved_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("edited_count", sa.Integer(), nullable=False),
        sa.Column("session_creation_ms", sa.Integer(), nullable=False),
        sa.Column("failed_complete_attempts", sa.Integer(), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('waiting_for_review', 'completed')",
            name="ck_review_sessions_status",
        ),
        sa.CheckConstraint(
            "(status = 'waiting_for_review' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name="ck_review_sessions_completion_timestamp",
        ),
        sa.CheckConstraint("proposal_set_version >= 1", name="ck_review_sessions_proposal_version"),
        sa.CheckConstraint("required_item_count >= 0", name="ck_review_sessions_required_count"),
        sa.CheckConstraint("optional_item_count >= 0", name="ck_review_sessions_optional_count"),
        sa.CheckConstraint("pending_count >= 0", name="ck_review_sessions_pending_count"),
        sa.CheckConstraint("approved_count >= 0", name="ck_review_sessions_approved_count"),
        sa.CheckConstraint("rejected_count >= 0", name="ck_review_sessions_rejected_count"),
        sa.CheckConstraint("edited_count >= 0", name="ck_review_sessions_edited_count"),
        sa.CheckConstraint("session_creation_ms >= 0", name="ck_review_sessions_creation_ms"),
        sa.CheckConstraint(
            "failed_complete_attempts >= 0",
            name="ck_review_sessions_failed_complete_attempts",
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["examination_run_id", "corpus_id", "analysis_run_id"],
            [
                "examination_runs.id",
                "examination_runs.corpus_id",
                "examination_runs.analysis_run_id",
            ],
            name="fk_review_sessions_examination_run_corpus_analysis",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_review_sessions_id_corpus"),
        sa.UniqueConstraint(
            "id",
            "corpus_id",
            "examination_run_id",
            name="uq_review_sessions_id_corpus_examination",
        ),
        sa.UniqueConstraint(
            "id",
            "corpus_id",
            "examination_run_id",
            "analysis_run_id",
            name="uq_review_sessions_id_corpus_examination_analysis",
        ),
        sa.UniqueConstraint(
            "corpus_id",
            "examination_run_id",
            name="uq_review_sessions_corpus_examination",
        ),
    )
    op.create_index("ix_review_sessions_corpus_id", "review_sessions", ["corpus_id"])
    op.create_index(
        "ix_review_sessions_examination_run_id",
        "review_sessions",
        ["examination_run_id"],
    )

    op.create_table(
        "review_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_session_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("proposed_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_edited_content", sa.Text(), nullable=True),
        sa.Column("edited_content_is_reviewer_authored", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected', 'edited')",
            name="ck_review_items_review_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(proposed_content) = 'object'",
            name="ck_review_items_proposed_object",
        ),
        sa.CheckConstraint("char_length(btrim(rule_id)) > 0", name="ck_review_items_rule_id"),
        sa.CheckConstraint(
            "(current_edited_content IS NULL AND "
            "edited_content_is_reviewer_authored IS FALSE) OR "
            "(current_edited_content IS NOT NULL AND "
            "char_length(btrim(current_edited_content)) > 0 AND "
            "edited_content_is_reviewer_authored IS TRUE)",
            name="ck_review_items_edited_content",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_review_items_id_corpus"),
        sa.UniqueConstraint(
            "id",
            "review_session_id",
            "corpus_id",
            name="uq_review_items_id_session_corpus",
        ),
        sa.UniqueConstraint(
            "review_session_id",
            "finding_id",
            name="uq_review_items_session_finding",
        ),
    )
    op.create_index("ix_review_items_corpus_id", "review_items", ["corpus_id"])
    op.create_index("ix_review_items_review_session_id", "review_items", ["review_session_id"])
    op.create_index("ix_review_items_finding_id", "review_items", ["finding_id"])

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("review_session_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("previous_status", sa.String(length=20), nullable=False),
        sa.Column("new_status", sa.String(length=20), nullable=False),
        sa.Column(
            "original_proposed_content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("edited_content", sa.Text(), nullable=True),
        sa.Column("edited_content_is_reviewer_authored", sa.Boolean(), nullable=False),
        sa.Column("reviewer_authored_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("decision_source", sa.String(length=20), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('approve', 'reject', 'edit')",
            name="ck_review_decisions_action",
        ),
        sa.CheckConstraint(
            "previous_status IN ('pending', 'approved', 'rejected', 'edited')",
            name="ck_review_decisions_previous_status",
        ),
        sa.CheckConstraint(
            "new_status IN ('pending', 'approved', 'rejected', 'edited')",
            name="ck_review_decisions_new_status",
        ),
        sa.CheckConstraint(
            "(action = 'approve' AND new_status = 'approved') OR "
            "(action = 'reject' AND new_status = 'rejected') OR "
            "(action = 'edit' AND new_status = 'edited')",
            name="ck_review_decisions_action_status",
        ),
        sa.CheckConstraint(
            "(action <> 'edit' AND edited_content IS NULL AND "
            "edited_content_is_reviewer_authored IS FALSE AND "
            "reviewer_authored_acknowledged IS FALSE) OR "
            "(action = 'edit' AND edited_content IS NOT NULL AND "
            "char_length(btrim(edited_content)) > 0 AND "
            "edited_content_is_reviewer_authored IS TRUE AND "
            "reviewer_authored_acknowledged IS TRUE)",
            name="ck_review_decisions_edit_content",
        ),
        sa.CheckConstraint(
            "decision_source IN ('api', 'ui')",
            name="ck_review_decisions_source",
        ),
        sa.CheckConstraint("char_length(btrim(actor)) > 0", name="ck_review_decisions_actor"),
        sa.ForeignKeyConstraint(
            ["review_item_id", "review_session_id", "corpus_id"],
            ["review_items.id", "review_items.review_session_id", "review_items.corpus_id"],
            name="fk_review_decisions_item_session_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_session_id", "corpus_id"],
            ["review_sessions.id", "review_sessions.corpus_id"],
            name="fk_review_decisions_session_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_review_decisions_id_corpus"),
    )
    op.create_index("ix_review_decisions_corpus_id", "review_decisions", ["corpus_id"])
    op.create_index(
        "ix_review_decisions_review_item_id",
        "review_decisions",
        ["review_item_id"],
    )
    op.create_index(
        "ix_review_decisions_review_session_id",
        "review_decisions",
        ["review_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_decisions_review_session_id", table_name="review_decisions")
    op.drop_index("ix_review_decisions_review_item_id", table_name="review_decisions")
    op.drop_index("ix_review_decisions_corpus_id", table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_index("ix_review_items_finding_id", table_name="review_items")
    op.drop_index("ix_review_items_review_session_id", table_name="review_items")
    op.drop_index("ix_review_items_corpus_id", table_name="review_items")
    op.drop_table("review_items")
    op.drop_index("ix_review_sessions_examination_run_id", table_name="review_sessions")
    op.drop_index("ix_review_sessions_corpus_id", table_name="review_sessions")
    op.drop_table("review_sessions")

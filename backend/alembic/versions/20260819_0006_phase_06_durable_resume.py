"""Create Phase 06 durable workflow, operation ledger, and checkpoint schema.

Revision ID: 20260819_0006
Revises: 20260819_0005
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260819_0006"
down_revision: str | None = "20260819_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_stage", sa.String(length=40), nullable=False),
        sa.Column("checkpoint_thread_id", sa.String(length=64), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=True),
        sa.Column("examination_run_id", sa.Uuid(), nullable=True),
        sa.Column("review_session_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("resume_count", sa.Integer(), nullable=False),
        sa.Column("graph_version", sa.String(length=100), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("error_action", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'waiting_for_review', 'failed', 'completed')",
            name="ck_workflow_runs_status",
        ),
        sa.CheckConstraint(
            "current_stage IN ("
            "'pending', 'understand', 'examine', 'open_review', "
            "'wait_for_review', 'finalize', 'completed'"
            ")",
            name="ck_workflow_runs_current_stage",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL)",
            name="ck_workflow_runs_completion_timestamp",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_workflow_runs_attempt_count"),
        sa.CheckConstraint("resume_count >= 0", name="ck_workflow_runs_resume_count"),
        sa.CheckConstraint(
            "char_length(btrim(checkpoint_thread_id)) > 0",
            name="ck_workflow_runs_checkpoint_thread_id",
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["analysis_run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_workflow_runs_analysis_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["examination_run_id", "corpus_id"],
            ["examination_runs.id", "examination_runs.corpus_id"],
            name="fk_workflow_runs_examination_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_session_id", "corpus_id"],
            ["review_sessions.id", "review_sessions.corpus_id"],
            name="fk_workflow_runs_review_session_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_workflow_runs_id_corpus"),
        sa.UniqueConstraint(
            "checkpoint_thread_id",
            name="uq_workflow_runs_checkpoint_thread_id",
        ),
    )
    op.create_index("ix_workflow_runs_corpus_id", "workflow_runs", ["corpus_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    op.create_table(
        "durable_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("operation_key", sa.String(length=64), nullable=False),
        sa.Column("operation_type", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("logical_operation_count", sa.Integer(), nullable=False),
        sa.Column("provider_attempt_count", sa.Integer(), nullable=False),
        sa.Column("provider_idempotency_id", sa.String(length=100), nullable=True),
        sa.Column("source_input_version", sa.String(length=64), nullable=False),
        sa.Column("model_provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('intended', 'in_flight', 'completed', 'failed', 'ambiguous')",
            name="ck_durable_operations_status",
        ),
        sa.CheckConstraint(
            "logical_operation_count IN (0, 1)",
            name="ck_durable_operations_logical_count",
        ),
        sa.CheckConstraint(
            "provider_attempt_count >= 0",
            name="ck_durable_operations_attempt_count",
        ),
        sa.CheckConstraint(
            "status <> 'intended' OR (logical_operation_count = 0 AND provider_attempt_count = 0)",
            name="ck_durable_operations_intended",
        ),
        sa.CheckConstraint(
            "status <> 'in_flight' OR "
            "(logical_operation_count = 0 AND provider_attempt_count >= 1)",
            name="ck_durable_operations_in_flight",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR ("
            "result_hash IS NOT NULL AND char_length(btrim(result_hash)) = 64 "
            "AND logical_operation_count = 1 AND provider_attempt_count >= 1"
            ")",
            name="ck_durable_operations_completed",
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR logical_operation_count = 0",
            name="ck_durable_operations_failed",
        ),
        sa.CheckConstraint(
            "status <> 'ambiguous' OR "
            "(logical_operation_count = 0 AND provider_attempt_count >= 1)",
            name="ck_durable_operations_ambiguous",
        ),
        sa.CheckConstraint(
            "char_length(btrim(operation_key)) = 64",
            name="ck_durable_operations_operation_key",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "corpus_id"],
            ["workflow_runs.id", "workflow_runs.corpus_id"],
            name="fk_durable_operations_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_key", name="uq_durable_operations_operation_key"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_durable_operations_id_corpus"),
    )
    op.create_index("ix_durable_operations_corpus_id", "durable_operations", ["corpus_id"])
    op.create_index(
        "ix_durable_operations_workflow_run_id",
        "durable_operations",
        ["workflow_run_id"],
    )

    op.create_table(
        "workflow_run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("stage_name", sa.String(length=40), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_workflow_run_events_ms",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "corpus_id"],
            ["workflow_runs.id", "workflow_runs.corpus_id"],
            name="fk_workflow_run_events_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_workflow_run_events_id_corpus"),
    )
    op.create_index("ix_workflow_run_events_corpus_id", "workflow_run_events", ["corpus_id"])
    op.create_index(
        "ix_workflow_run_events_workflow_run_id",
        "workflow_run_events",
        ["workflow_run_id"],
    )

    op.create_table(
        "checkpoint_migrations",
        sa.Column("v", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("v"),
    )
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"])
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "channel", "version"),
    )
    op.create_index("checkpoint_blobs_thread_id_idx", "checkpoint_blobs", ["thread_id"])
    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column("task_path", sa.Text(), server_default="", nullable=False),
        sa.PrimaryKeyConstraint(
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            "task_id",
            "idx",
        ),
    )
    op.create_index("checkpoint_writes_thread_id_idx", "checkpoint_writes", ["thread_id"])
    op.execute(
        sa.text(
            "INSERT INTO checkpoint_migrations (v) VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)"
        )
    )


def downgrade() -> None:
    op.drop_index("checkpoint_writes_thread_id_idx", table_name="checkpoint_writes")
    op.drop_table("checkpoint_writes")
    op.drop_index("checkpoint_blobs_thread_id_idx", table_name="checkpoint_blobs")
    op.drop_table("checkpoint_blobs")
    op.drop_index("checkpoints_thread_id_idx", table_name="checkpoints")
    op.drop_table("checkpoints")
    op.drop_table("checkpoint_migrations")
    op.drop_index("ix_workflow_run_events_workflow_run_id", table_name="workflow_run_events")
    op.drop_index("ix_workflow_run_events_corpus_id", table_name="workflow_run_events")
    op.drop_table("workflow_run_events")
    op.drop_index("ix_durable_operations_workflow_run_id", table_name="durable_operations")
    op.drop_index("ix_durable_operations_corpus_id", table_name="durable_operations")
    op.drop_table("durable_operations")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_corpus_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")

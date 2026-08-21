"""Create Phase 07 incremental revision, evidence, and watcher schema.

Revision ID: 20260819_0007
Revises: 20260819_0006
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260819_0007"
down_revision: str | None = "20260819_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_source_versions_id_source_corpus",
        "source_versions",
        ["id", "source_id", "corpus_id"],
    )
    op.create_unique_constraint(
        "uq_source_versions_id_source_corpus_sha256",
        "source_versions",
        ["id", "source_id", "corpus_id", "sha256"],
    )
    op.create_table(
        "corpus_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("examination_run_id", sa.Uuid(), nullable=False),
        sa.Column("review_session_id", sa.Uuid(), nullable=True),
        sa.Column("source_version_set", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=100), nullable=False),
        sa.Column("understand_graph_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_config_version", sa.String(length=100), nullable=False),
        sa.Column("ruleset_version", sa.String(length=100), nullable=False),
        sa.Column("examine_graph_version", sa.String(length=100), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("revision_number >= 1", name="ck_corpus_revisions_number"),
        sa.CheckConstraint(
            "char_length(btrim(taxonomy_version)) > 0",
            name="ck_corpus_revisions_taxonomy_version",
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["analysis_run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_corpus_revisions_analysis_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["examination_run_id", "corpus_id"],
            ["examination_runs.id", "examination_runs.corpus_id"],
            name="fk_corpus_revisions_examination_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_session_id", "corpus_id"],
            ["review_sessions.id", "review_sessions.corpus_id"],
            name="fk_corpus_revisions_review_session_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_corpus_revisions_id_corpus"),
        sa.UniqueConstraint(
            "corpus_id",
            "revision_number",
            name="uq_corpus_revisions_corpus_number",
        ),
    )
    op.create_index("ix_corpus_revisions_corpus_id", "corpus_revisions", ["corpus_id"])
    op.create_index(
        "uq_corpus_revisions_current",
        "corpus_revisions",
        ["corpus_id"],
        unique=True,
        postgresql_where=sa.text("is_current IS TRUE"),
    )

    op.create_table(
        "corpus_revision_sources",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("logical_name", sa.String(length=255), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(sha256)) = 64",
            name="ck_corpus_revision_sources_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id", "corpus_id"],
            ["corpus_revisions.id", "corpus_revisions.corpus_id"],
            name="fk_corpus_revision_sources_revision_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "corpus_id"],
            ["sources.id", "sources.corpus_id"],
            name="fk_corpus_revision_sources_source_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id", "source_id", "corpus_id", "sha256"],
            [
                "source_versions.id",
                "source_versions.source_id",
                "source_versions.corpus_id",
                "source_versions.sha256",
            ],
            name="fk_corpus_revision_sources_version_source_corpus_sha256",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("revision_id", "source_id"),
        sa.UniqueConstraint(
            "revision_id",
            "source_version_id",
            name="uq_corpus_revision_sources_revision_version",
        ),
    )
    op.create_index(
        "ix_corpus_revision_sources_corpus_id",
        "corpus_revision_sources",
        ["corpus_id"],
    )

    op.create_table(
        "incremental_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_revision_id", sa.Uuid(), nullable=False),
        sa.Column("result_revision_id", sa.Uuid(), nullable=True),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=True),
        sa.Column("examination_run_id", sa.Uuid(), nullable=True),
        sa.Column("review_session_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("change_kind", sa.String(length=40), nullable=False),
        sa.Column("impact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("measurement", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("error_action", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'stale_baseline')",
            name="ck_incremental_runs_status",
        ),
        sa.CheckConstraint(
            "change_kind IN ("
            "'unchanged', 'changed', 'added', 'removed', 'mixed', 'stale_baseline'"
            ")",
            name="ck_incremental_runs_change_kind",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL)",
            name="ck_incremental_runs_completion_timestamp",
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["baseline_revision_id", "corpus_id"],
            ["corpus_revisions.id", "corpus_revisions.corpus_id"],
            name="fk_incremental_runs_baseline_revision_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_revision_id", "corpus_id"],
            ["corpus_revisions.id", "corpus_revisions.corpus_id"],
            name="fk_incremental_runs_result_revision_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id", "corpus_id"],
            ["analysis_runs.id", "analysis_runs.corpus_id"],
            name="fk_incremental_runs_analysis_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["examination_run_id", "corpus_id"],
            ["examination_runs.id", "examination_runs.corpus_id"],
            name="fk_incremental_runs_examination_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_session_id", "corpus_id"],
            ["review_sessions.id", "review_sessions.corpus_id"],
            name="fk_incremental_runs_review_session_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_incremental_runs_id_corpus"),
    )
    op.create_index("ix_incremental_runs_corpus_id", "incremental_runs", ["corpus_id"])
    op.create_index(
        "ix_incremental_runs_baseline_revision_id",
        "incremental_runs",
        ["baseline_revision_id"],
    )

    op.create_table(
        "incremental_artifact_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("incremental_run_id", sa.Uuid(), nullable=False),
        sa.Column("durable_operation_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_kind", sa.String(length=40), nullable=False),
        sa.Column("artifact_id", sa.String(length=100), nullable=False),
        sa.Column("disposition", sa.String(length=30), nullable=False),
        sa.Column("canonical_hash_before", sa.String(length=64), nullable=True),
        sa.Column("canonical_hash_after", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "artifact_kind IN ("
            "'fact', 'contradiction', 'finding', 'review_item', 'operation', "
            "'stage', 'source_version', 'source_block', 'rule'"
            ")",
            name="ck_incremental_artifact_kind",
        ),
        sa.CheckConstraint(
            "disposition IN ("
            "'reused', 'recomputed', 'added', 'removed', 'executed', "
            "'skipped', 'unchanged', 'obsolete'"
            ")",
            name="ck_incremental_artifact_disposition",
        ),
        sa.CheckConstraint(
            "canonical_hash_before IS NULL OR char_length(btrim(canonical_hash_before)) = 64",
            name="ck_incremental_artifact_hash_before",
        ),
        sa.CheckConstraint(
            "canonical_hash_after IS NULL OR char_length(btrim(canonical_hash_after)) = 64",
            name="ck_incremental_artifact_hash_after",
        ),
        sa.ForeignKeyConstraint(
            ["incremental_run_id", "corpus_id"],
            ["incremental_runs.id", "incremental_runs.corpus_id"],
            name="fk_incremental_artifact_evidence_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["durable_operation_id", "corpus_id"],
            ["durable_operations.id", "durable_operations.corpus_id"],
            name="fk_incremental_artifact_evidence_operation_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "corpus_id",
            name="uq_incremental_artifact_evidence_id_corpus",
        ),
    )
    op.create_index(
        "ix_incremental_artifact_evidence_corpus_id",
        "incremental_artifact_evidence",
        ["corpus_id"],
    )
    op.create_index(
        "ix_incremental_artifact_evidence_run_id",
        "incremental_artifact_evidence",
        ["incremental_run_id"],
    )

    op.create_table(
        "watcher_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inbox_root", sa.String(length=500), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=True),
        sa.Column("logical_name", sa.String(length=255), nullable=True),
        sa.Column("declared_format", sa.String(length=20), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("stable_poll_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_incremental_run_id", sa.Uuid(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("byte_size >= 0", name="ck_watcher_files_byte_size"),
        sa.CheckConstraint("stable_poll_count >= 0", name="ck_watcher_files_stable_polls"),
        sa.CheckConstraint(
            "status IN ("
            "'observing', 'stable', 'ingested_incremental_pending', "
            "'processing_incremental', 'completed', 'failed_retryable', "
            "'failed_terminal', 'unchanged', 'missing'"
            ")",
            name="ck_watcher_files_status",
        ),
        sa.CheckConstraint(
            "content_sha256 IS NULL OR char_length(btrim(content_sha256)) = 64",
            name="ck_watcher_files_sha256",
        ),
        sa.CheckConstraint(
            "declared_format IS NULL OR declared_format IN ('pdf', 'docx', 'markdown', 'txt')",
            name="ck_watcher_files_declared_format",
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["last_incremental_run_id", "corpus_id"],
            ["incremental_runs.id", "incremental_runs.corpus_id"],
            name="fk_watcher_files_incremental_run_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "inbox_root",
            "relative_path",
            name="uq_watcher_files_root_path",
        ),
    )
    op.create_index("ix_watcher_files_corpus_id", "watcher_files", ["corpus_id"])
    op.create_index(
        "ix_watcher_files_content_sha256",
        "watcher_files",
        ["corpus_id", "content_sha256"],
    )

    op.alter_column(
        "durable_operations",
        "workflow_run_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.add_column(
        "durable_operations",
        sa.Column("incremental_run_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_durable_operations_incremental_run_corpus",
        "durable_operations",
        "incremental_runs",
        ["incremental_run_id", "corpus_id"],
        ["id", "corpus_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_durable_operations_owner",
        "durable_operations",
        "("
        "workflow_run_id IS NOT NULL AND incremental_run_id IS NULL"
        ") OR ("
        "workflow_run_id IS NULL AND incremental_run_id IS NOT NULL"
        ")",
    )
    op.create_index(
        "ix_durable_operations_incremental_run_id",
        "durable_operations",
        ["incremental_run_id"],
    )


def downgrade() -> None:
    # Drop Phase 07 dependents first. Incremental DurableOperation rows have
    # workflow_run_id NULL; restoring NOT NULL before deleting them fails.
    op.execute(sa.text("DROP INDEX IF EXISTS ix_watcher_files_content_sha256"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_watcher_files_corpus_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS watcher_files"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_incremental_artifact_evidence_run_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_incremental_artifact_evidence_corpus_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS incremental_artifact_evidence"))
    op.execute(
        sa.text(
            "DELETE FROM durable_operations "
            "WHERE incremental_run_id IS NOT NULL OR workflow_run_id IS NULL"
        )
    )
    op.execute(sa.text("DROP INDEX IF EXISTS ix_durable_operations_incremental_run_id"))
    op.execute(
        sa.text(
            "ALTER TABLE durable_operations DROP CONSTRAINT IF EXISTS ck_durable_operations_owner"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE durable_operations "
            "DROP CONSTRAINT IF EXISTS fk_durable_operations_incremental_run_corpus"
        )
    )
    op.execute(sa.text("ALTER TABLE durable_operations DROP COLUMN IF EXISTS incremental_run_id"))
    op.alter_column(
        "durable_operations",
        "workflow_run_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.execute(sa.text("DROP INDEX IF EXISTS ix_incremental_runs_baseline_revision_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_incremental_runs_corpus_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS incremental_runs"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_corpus_revision_sources_corpus_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS corpus_revision_sources"))
    op.execute(
        sa.text(
            "ALTER TABLE source_versions DROP CONSTRAINT IF EXISTS "
            "uq_source_versions_id_source_corpus_sha256"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE source_versions DROP CONSTRAINT IF EXISTS "
            "uq_source_versions_id_source_corpus"
        )
    )
    op.drop_index("uq_corpus_revisions_current", table_name="corpus_revisions")
    op.drop_index("ix_corpus_revisions_corpus_id", table_name="corpus_revisions")
    op.drop_table("corpus_revisions")

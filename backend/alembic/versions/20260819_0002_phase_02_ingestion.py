"""Create the Phase 02 corpus, source, version, and block schema.

Revision ID: 20260819_0002
Revises: 20260819_0001
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260819_0002"
down_revision: str | None = "20260819_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corpora",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=200), nullable=False),
        sa.Column("declared_formats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("logical_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["corpora.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("corpus_id", "logical_name", name="uq_sources_corpus_logical_name"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_sources_id_corpus"),
    )
    op.create_index("ix_sources_corpus_id", "sources", ["corpus_id"])

    op.create_table(
        "source_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("declared_format", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("parser_status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("byte_size >= 0", name="ck_source_versions_byte_size"),
        sa.CheckConstraint(
            "declared_format IN ('pdf', 'docx', 'markdown', 'txt')",
            name="ck_source_versions_declared_format",
        ),
        sa.CheckConstraint("parser_status = 'parsed'", name="ck_source_versions_parser_status"),
        sa.ForeignKeyConstraint(
            ["source_id", "corpus_id"],
            ["sources.id", "sources.corpus_id"],
            name="fk_source_versions_source_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "corpus_id", name="uq_source_versions_id_corpus"),
        sa.UniqueConstraint("source_id", "sha256", name="uq_source_versions_source_sha256"),
        sa.UniqueConstraint("storage_key", name="uq_source_versions_storage_key"),
    )
    op.create_index("ix_source_versions_corpus_id", "source_versions", ["corpus_id"])
    op.create_index("ix_source_versions_source_id", "source_versions", ["source_id"])

    op.create_table(
        "source_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=50), nullable=False),
        sa.Column("native_locator", sa.String(length=255), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("normalized_start", sa.Integer(), nullable=False),
        sa.Column("normalized_end", sa.Integer(), nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.VECTOR(dim=64),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint("block_index >= 0", name="ck_source_blocks_block_index"),
        sa.CheckConstraint(
            "normalized_end = char_length(normalized_text)",
            name="ck_source_blocks_end",
        ),
        sa.CheckConstraint("normalized_start = 0", name="ck_source_blocks_start"),
        sa.ForeignKeyConstraint(
            ["source_version_id", "corpus_id"],
            ["source_versions.id", "source_versions.corpus_id"],
            name="fk_source_blocks_version_corpus",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_version_id", "block_index", name="uq_source_blocks_version_index"
        ),
        sa.UniqueConstraint(
            "source_version_id", "native_locator", name="uq_source_blocks_version_locator"
        ),
    )
    op.create_index("ix_source_blocks_corpus_id", "source_blocks", ["corpus_id"])
    op.create_index("ix_source_blocks_version_id", "source_blocks", ["source_version_id"])
    op.execute(
        "CREATE INDEX ix_source_blocks_embedding_hnsw "
        "ON source_blocks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_source_blocks_embedding_hnsw", table_name="source_blocks")
    op.drop_index("ix_source_blocks_version_id", table_name="source_blocks")
    op.drop_index("ix_source_blocks_corpus_id", table_name="source_blocks")
    op.drop_table("source_blocks")
    op.drop_index("ix_source_versions_source_id", table_name="source_versions")
    op.drop_index("ix_source_versions_corpus_id", table_name="source_versions")
    op.drop_table("source_versions")
    op.drop_index("ix_sources_corpus_id", table_name="sources")
    op.drop_table("sources")
    op.drop_table("corpora")

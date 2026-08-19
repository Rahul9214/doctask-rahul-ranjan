from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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

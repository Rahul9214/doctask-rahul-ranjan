import os
import threading
from pathlib import Path

import pytest
from alembic.config import Config
from helpers import ingest_corpus, make_publication, mixed_review_then_complete
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.config import get_settings
from app.services import Phase02Service
from app.storage import LocalFileStorage

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_TABLES = (
    "publication_events",
    "published_register_item_contradictions",
    "published_register_item_facts",
    "published_register_items",
    "published_registers",
)
FINAL_CHAIN_CONSTRAINTS = {
    "workflow_runs": {
        "fk_workflow_runs_examination_chain",
        "fk_workflow_runs_review_chain",
        "uq_workflow_runs_id_corpus_chain",
    },
    "corpus_revisions": {
        "fk_corpus_revisions_examination_chain",
        "fk_corpus_revisions_review_chain",
        "uq_corpus_revisions_id_corpus_chain",
    },
    "review_items": {"uq_review_items_id_session_corpus_chain_finding"},
    "published_registers": {
        "fk_published_registers_review_chain",
        "fk_published_registers_examination_chain",
        "fk_published_registers_workflow_chain",
        "fk_published_registers_revision_chain",
        "uq_published_registers_id_corpus_chain",
    },
    "published_register_items": {
        "fk_published_register_items_register_chain",
        "fk_published_register_items_review_item_chain",
        "fk_published_register_items_finding_chain",
        "uq_published_register_items_id_register_corpus_analysis",
    },
    "published_register_item_facts": {
        "fk_published_item_facts_item_register_corpus_analysis",
        "fk_published_item_facts_fact_run_corpus",
    },
    "published_register_item_contradictions": {
        "fk_published_item_contradictions_item_register_analysis",
        "fk_published_item_contradictions_contradiction",
    },
}
LATE_CORRECTION_CONSTRAINTS = {
    "workflow_runs": FINAL_CHAIN_CONSTRAINTS["workflow_runs"],
    "corpus_revisions": FINAL_CHAIN_CONSTRAINTS["corpus_revisions"],
    "review_items": FINAL_CHAIN_CONSTRAINTS["review_items"],
    "published_registers": {
        "fk_published_registers_examination_chain",
        "fk_published_registers_workflow_chain",
        "fk_published_registers_revision_chain",
        "uq_published_registers_id_corpus_chain",
    },
    "published_register_items": {
        "fk_published_register_items_register_chain",
        "fk_published_register_items_review_item_chain",
        "uq_published_register_items_id_register_corpus_analysis",
    },
    "published_register_item_facts": {"fk_published_item_facts_item_register_corpus_analysis"},
    "published_register_item_contradictions": {
        "fk_published_item_contradictions_item_register_analysis"
    },
}


def _migrate(direction: str, target: str) -> None:
    application_url = os.environ["DATABASE_URL"]
    test_url = os.environ["TEST_DATABASE_URL"]
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            os.environ["DATABASE_URL"] = test_url
            get_settings.cache_clear()
            config = Config(str(BACKEND_ROOT / "alembic.ini"))
            if direction == "downgrade":
                command.downgrade(config, target)
            elif direction == "upgrade":
                command.upgrade(config, target)
            else:
                raise ValueError(f"unsupported alembic direction {direction!r}")
        except BaseException as exc:
            errors.append(exc)
        finally:
            os.environ["DATABASE_URL"] = application_url
            get_settings.cache_clear()

    thread = threading.Thread(target=worker, name=f"alembic-{direction}")
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


async def _constraint_names(session: AsyncSession, table_name: str) -> set[str]:
    rows = await session.scalars(
        text(
            """
            SELECT constraint_row.conname
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation_row
              ON relation_row.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace_row
              ON namespace_row.oid = relation_row.relnamespace
            WHERE namespace_row.nspname = 'public'
              AND relation_row.relname = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {str(name) for name in rows}


async def _simulate_older_stamped_0008(session: AsyncSession) -> None:
    statements = (
        """
        ALTER TABLE published_register_item_facts
        DROP CONSTRAINT fk_published_item_facts_item_register_corpus_analysis
        """,
        """
        ALTER TABLE published_register_item_facts
        ADD CONSTRAINT fk_published_item_facts_item_register_corpus
        FOREIGN KEY (published_item_id, published_register_id, corpus_id)
        REFERENCES published_register_items (id, published_register_id, corpus_id)
        ON DELETE RESTRICT
        """,
        """
        ALTER TABLE published_register_item_contradictions
        DROP CONSTRAINT fk_published_item_contradictions_item_register_analysis
        """,
        """
        ALTER TABLE published_register_item_contradictions
        ADD CONSTRAINT fk_published_item_contradictions_item_register
        FOREIGN KEY (published_item_id, published_register_id, corpus_id)
        REFERENCES published_register_items (id, published_register_id, corpus_id)
        ON DELETE RESTRICT
        """,
        """
        ALTER TABLE published_register_items
        DROP CONSTRAINT fk_published_register_items_register_chain
        """,
        """
        ALTER TABLE published_register_items
        ADD CONSTRAINT fk_published_register_items_register_corpus
        FOREIGN KEY (published_register_id, corpus_id)
        REFERENCES published_registers (id, corpus_id)
        ON DELETE RESTRICT
        """,
        """
        ALTER TABLE published_register_items
        DROP CONSTRAINT fk_published_register_items_review_item_chain
        """,
        """
        ALTER TABLE published_register_items
        ADD CONSTRAINT fk_published_register_items_review_item
        FOREIGN KEY (review_item_id, review_session_id, corpus_id)
        REFERENCES review_items (id, review_session_id, corpus_id)
        ON DELETE RESTRICT
        """,
        """
        ALTER TABLE published_registers
        DROP CONSTRAINT fk_published_registers_examination_chain
        """,
        """
        ALTER TABLE published_registers
        DROP CONSTRAINT fk_published_registers_workflow_chain
        """,
        """
        ALTER TABLE published_registers
        ADD CONSTRAINT fk_published_registers_workflow_corpus
        FOREIGN KEY (workflow_run_id, corpus_id)
        REFERENCES workflow_runs (id, corpus_id)
        ON DELETE RESTRICT
        """,
        """
        ALTER TABLE published_registers
        DROP CONSTRAINT fk_published_registers_revision_chain
        """,
        """
        ALTER TABLE published_registers
        ADD CONSTRAINT fk_published_registers_revision_corpus
        FOREIGN KEY (corpus_revision_id, corpus_id)
        REFERENCES corpus_revisions (id, corpus_id)
        ON DELETE RESTRICT
        """,
        """
        ALTER TABLE published_registers
        DROP CONSTRAINT uq_published_registers_id_corpus_chain
        """,
        """
        ALTER TABLE published_register_items
        DROP CONSTRAINT uq_published_register_items_id_register_corpus_analysis
        """,
        """
        ALTER TABLE corpus_revisions
        DROP CONSTRAINT fk_corpus_revisions_review_chain
        """,
        """
        ALTER TABLE corpus_revisions
        DROP CONSTRAINT fk_corpus_revisions_examination_chain
        """,
        """
        ALTER TABLE workflow_runs
        DROP CONSTRAINT fk_workflow_runs_review_chain
        """,
        """
        ALTER TABLE workflow_runs
        DROP CONSTRAINT fk_workflow_runs_examination_chain
        """,
        """
        ALTER TABLE corpus_revisions
        DROP CONSTRAINT uq_corpus_revisions_id_corpus_chain
        """,
        """
        ALTER TABLE workflow_runs
        DROP CONSTRAINT uq_workflow_runs_id_corpus_chain
        """,
        """
        ALTER TABLE review_items
        DROP CONSTRAINT uq_review_items_id_session_corpus_chain_finding
        """,
    )
    for statement in statements:
        await session.execute(text(statement))
    await session.commit()


@pytest.mark.integration
async def test_publication_schema_round_trip_discards_publication_rows(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    publication = make_publication(phase02)
    analysis = await publication.review.examine.understand.create_run(corpus.id)
    exam = await publication.review.examine.create_run(corpus.id, analysis.id)
    session, _created = await publication.review.create_session(corpus.id, exam.id)
    await mixed_review_then_complete(publication.review, corpus.id, session.id)
    register, created = await publication.publish(corpus.id, session.id)
    assert created is True
    async with publication.session_factory() as session_db:
        before = {
            table: await session_db.scalar(text(f"SELECT to_regclass('public.{table}')"))
            for table in PUBLICATION_TABLES
        }
        version = await session_db.scalar(text("SELECT version_num FROM alembic_version"))
    assert all(value is not None for value in before.values())
    assert version == "20260822_0008"
    try:
        _migrate("downgrade", "20260819_0007")
        async with publication.session_factory() as session_db:
            after = {
                table: await session_db.scalar(text(f"SELECT to_regclass('public.{table}')"))
                for table in PUBLICATION_TABLES
            }
            review_survives = await session_db.scalar(
                text("SELECT id FROM review_sessions WHERE id = :id"),
                {"id": session.id},
            )
            version = await session_db.scalar(text("SELECT version_num FROM alembic_version"))
        assert all(value is None for value in after.values())
        assert review_survives == session.id
        assert version == "20260819_0007"
    finally:
        _migrate("upgrade", "head")
        async with publication.session_factory() as session_db:
            restored = await session_db.scalar(text("SELECT version_num FROM alembic_version"))
            tables = {
                table: await session_db.scalar(text(f"SELECT to_regclass('public.{table}')"))
                for table in PUBLICATION_TABLES
            }
        assert restored == "20260822_0008"
        assert all(value is not None for value in tables.values())
        with pytest.raises(Exception) as error:
            await publication.get_register(corpus.id, register.id)
        assert getattr(error.value, "code", None) == "publication_not_found"


@pytest.mark.integration
async def test_older_stamped_0008_downgrades_and_reupgrades_with_final_constraints(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Older stamped 0008 recovery",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    try:
        _migrate("downgrade", "20260819_0007")
        _migrate("upgrade", "20260822_0008")
        async with phase02.session_factory() as session:
            await _simulate_older_stamped_0008(session)
            version = await session.scalar(text("SELECT version_num FROM alembic_version"))
            absent_constraints = set()
            for table_name, expected in LATE_CORRECTION_CONSTRAINTS.items():
                names = await _constraint_names(session, table_name)
                absent_constraints.update(expected - names)
        assert version == "20260822_0008"
        assert absent_constraints == {
            constraint
            for expected in LATE_CORRECTION_CONSTRAINTS.values()
            for constraint in expected
        }

        _migrate("downgrade", "20260819_0007")
        async with phase02.session_factory() as session:
            version = await session.scalar(text("SELECT version_num FROM alembic_version"))
            corpus_survives = await session.scalar(
                text("SELECT id FROM corpora WHERE id = :corpus_id"),
                {"corpus_id": corpus.id},
            )
        assert version == "20260819_0007"
        assert corpus_survives == corpus.id

        _migrate("upgrade", "20260822_0008")
        async with phase02.session_factory() as session:
            version = await session.scalar(text("SELECT version_num FROM alembic_version"))
            for table_name, expected in FINAL_CHAIN_CONSTRAINTS.items():
                assert expected <= await _constraint_names(session, table_name)
        assert version == "20260822_0008"
    finally:
        _migrate("downgrade", "20260819_0007")
        _migrate("upgrade", "20260822_0008")

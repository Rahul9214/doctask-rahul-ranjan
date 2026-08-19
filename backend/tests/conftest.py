import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.services import Phase02Service
from app.storage import LocalFileStorage
from app.test_database import assert_destructive_test_database


@pytest.fixture
def corpus_fixtures() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "corpora"


@pytest.fixture
async def phase02_service(
    tmp_path: Path,
) -> AsyncIterator[tuple[Phase02Service, LocalFileStorage]]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    application_database_url = Settings().sqlalchemy_database_url()
    assert_destructive_test_database(
        test_database_url=database_url,
        application_database_url=application_database_url,
        allow_destructive=os.getenv("ALLOW_DESTRUCTIVE_TEST_DATABASE"),
    )
    engine = create_engine(Settings(database_url=SecretStr(database_url)))
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE finding_fact_evidence, finding_contradiction_evidence, "
                "examination_stage_events, findings, examination_runs, "
                "contradictions, facts, stage_events, analysis_runs, "
                "source_blocks, source_versions, sources, corpora CASCADE"
            )
        )
    storage = LocalFileStorage(tmp_path / "sources", max_upload_bytes=10 * 1024 * 1024)
    service = Phase02Service(create_session_factory(engine), storage)
    try:
        yield service, storage
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE finding_fact_evidence, finding_contradiction_evidence, "
                    "examination_stage_events, findings, examination_runs, "
                    "contradictions, facts, stage_events, analysis_runs, "
                    "source_blocks, source_versions, sources, corpora CASCADE"
                )
            )
        await engine.dispose()

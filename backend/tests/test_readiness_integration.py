import os

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.db import check_dependencies, create_engine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ready_with_postgresql_and_pgvector() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not set")

    settings = Settings(database_url=SecretStr(database_url))
    engine = create_engine(settings)
    try:
        report = await check_dependencies(engine, timeout_seconds=5)
    finally:
        await engine.dispose()

    assert report.status == "ready"
    assert report.checks["database"].status == "ready"
    assert report.checks["pgvector"].status == "ready"
    assert report.checks["pgvector"].version is not None

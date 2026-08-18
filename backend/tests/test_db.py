from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import check_dependencies


def engine_with_vector_version(version: str | None) -> AsyncEngine:
    result = MagicMock()
    result.scalar_one_or_none.return_value = version

    connection = MagicMock()
    connection.execute = AsyncMock(side_effect=[MagicMock(), result])

    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(return_value=connection)
    connection_context.__aexit__ = AsyncMock(return_value=None)

    engine = MagicMock()
    engine.connect.return_value = connection_context
    return cast(AsyncEngine, engine)


@pytest.mark.asyncio
async def test_dependency_check_reports_pgvector_version() -> None:
    report = await check_dependencies(engine_with_vector_version("0.8.1"), timeout_seconds=1)

    assert report.status == "ready"
    assert report.checks["pgvector"].version == "0.8.1"


@pytest.mark.asyncio
async def test_dependency_check_reports_missing_pgvector_actionably() -> None:
    report = await check_dependencies(engine_with_vector_version(None), timeout_seconds=1)

    assert report.status == "unavailable"
    assert report.checks["database"].status == "ready"
    assert report.checks["pgvector"].status == "unavailable"
    assert report.checks["pgvector"].action == "Run `uv run alembic upgrade head` and retry."

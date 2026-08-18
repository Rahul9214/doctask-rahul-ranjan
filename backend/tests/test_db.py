import asyncio
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


def engine_with_connect_error(error: BaseException) -> AsyncEngine:
    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(side_effect=error)
    connection_context.__aexit__ = AsyncMock(return_value=None)

    engine = MagicMock()
    engine.connect.return_value = connection_context
    return cast(AsyncEngine, engine)


def engine_with_hanging_connect() -> AsyncEngine:
    async def hang() -> None:
        await asyncio.sleep(60)

    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(side_effect=hang)
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


@pytest.mark.asyncio
async def test_connection_refusal_is_translated_without_raw_error_details() -> None:
    raw_detail = "Connect call failed ('127.0.0.1', 1)"

    report = await check_dependencies(
        engine_with_connect_error(ConnectionRefusedError(raw_detail)),
        timeout_seconds=1,
    )

    payload = report.model_dump_json()
    assert report.status == "unavailable"
    assert report.checks["database"].detail == "PostgreSQL connection failed."
    assert report.checks["database"].action
    assert raw_detail not in payload
    assert "ConnectionRefusedError" not in payload


@pytest.mark.asyncio
async def test_dependency_timeout_is_translated_actionably() -> None:
    report = await check_dependencies(engine_with_hanging_connect(), timeout_seconds=0.01)

    assert report.status == "unavailable"
    assert report.checks["database"].detail == "Database readiness check timed out."
    assert report.checks["database"].action


@pytest.mark.asyncio
async def test_unexpected_programming_error_is_not_swallowed() -> None:
    with pytest.raises(ValueError, match="programming defect"):
        await check_dependencies(
            engine_with_connect_error(ValueError("programming defect")),
            timeout_seconds=1,
        )

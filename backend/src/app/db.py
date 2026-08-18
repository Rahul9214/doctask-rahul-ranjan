import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


class DependencyCheck(BaseModel):
    status: Literal["ready", "unavailable"]
    version: str | None = None
    detail: str | None = None
    action: str | None = None


class ReadinessReport(BaseModel):
    status: Literal["ready", "unavailable"]
    checks: dict[str, DependencyCheck]


ReadinessProbe = Callable[[], Awaitable[ReadinessReport]]
SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.sqlalchemy_database_url(),
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False)


async def check_dependencies(engine: AsyncEngine, timeout_seconds: float) -> ReadinessReport:
    try:
        async with asyncio.timeout(timeout_seconds):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                result = await connection.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
                vector_version = result.scalar_one_or_none()
    except TimeoutError:
        return _database_unavailable(
            detail="Database readiness check timed out.",
            action="Verify PostgreSQL is running and DATABASE_URL is reachable.",
        )
    except SQLAlchemyError:
        return _database_unavailable(
            detail="PostgreSQL connection failed.",
            action="Verify PostgreSQL is running, credentials are valid, and migrations completed.",
        )

    if vector_version is None:
        return ReadinessReport(
            status="unavailable",
            checks={
                "database": DependencyCheck(status="ready"),
                "pgvector": DependencyCheck(
                    status="unavailable",
                    detail="The PostgreSQL vector extension is not enabled.",
                    action="Run `uv run alembic upgrade head` and retry.",
                ),
            },
        )

    return ReadinessReport(
        status="ready",
        checks={
            "database": DependencyCheck(status="ready"),
            "pgvector": DependencyCheck(status="ready", version=str(vector_version)),
        },
    )


def _database_unavailable(*, detail: str, action: str) -> ReadinessReport:
    return ReadinessReport(
        status="unavailable",
        checks={
            "database": DependencyCheck(
                status="unavailable",
                detail=detail,
                action=action,
            ),
            "pgvector": DependencyCheck(
                status="unavailable",
                detail="Not checked because PostgreSQL is unavailable.",
                action="Restore PostgreSQL connectivity first.",
            ),
        },
    )

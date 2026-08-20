"""PostgreSQL LangGraph checkpointer connection helpers."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url


def configure_windows_psycopg_loop() -> None:
    """Use SelectorEventLoop on Windows so psycopg async can connect.

    Linux/macOS are unchanged. Must run before the process event loop starts.
    """

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def psycopg_conninfo(database_url: str) -> str:
    """Convert a SQLAlchemy asyncpg URL into a psycopg connection string."""

    url = make_url(database_url)
    if url.drivername.startswith("postgresql"):
        url = url.set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


@asynccontextmanager
async def open_postgres_checkpointer(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    conninfo = psycopg_conninfo(database_url)
    async with AsyncPostgresSaver.from_conn_string(conninfo) as saver:
        await saver.setup()
        yield saver

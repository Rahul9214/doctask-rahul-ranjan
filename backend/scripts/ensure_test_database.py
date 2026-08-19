"""Create the fixed disposable integration database when it does not exist."""

import asyncio
import os

import asyncpg
from sqlalchemy.engine import make_url

from app.test_database import TEST_DATABASE_NAME


async def ensure_test_database() -> None:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        raise SystemExit("DATABASE_URL must identify the local application database.")

    url = make_url(database_url)
    if url.database == TEST_DATABASE_NAME:
        raise SystemExit("DATABASE_URL must not already identify the disposable test database.")

    connection = await asyncpg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.database,
    )
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            TEST_DATABASE_NAME,
        )
        if exists is None:
            await connection.execute(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(ensure_test_database())

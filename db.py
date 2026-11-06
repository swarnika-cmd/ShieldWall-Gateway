"""Postgres access.

The API uses psycopg 3's AsyncConnectionPool: connections are checked out
with `async with pool.connection()`, so the event loop is never blocked and
a connection is never shared by two coroutines at once.

The Celery worker and the CLI scripts use plain synchronous psycopg
connections (see sync_connect). Same driver, same SQL, same placeholders.
"""
import asyncio
import logging
import os
import time
from typing import Any, List, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

import config

logger = logging.getLogger("shieldwall.db")

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def read_schema() -> str:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return f.read()


async def create_pool(retries: int = 10, delay: float = 1.0) -> AsyncConnectionPool:
    """Open the pool, waiting for Postgres to come up (docker compose start order)."""
    pool = AsyncConnectionPool(
        config.DATABASE_URL,
        min_size=config.DB_POOL_MIN,
        max_size=config.DB_POOL_MAX,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    for attempt in range(1, retries + 1):
        try:
            await pool.open(wait=True, timeout=5)
            return pool
        except Exception as exc:
            if attempt == retries:
                raise
            logger.warning("Postgres not ready (attempt %d/%d): %s", attempt, retries, exc)
            await asyncio.sleep(delay)
    return pool


async def apply_schema(pool: AsyncConnectionPool) -> None:
    """Run schema.sql. Idempotent, guarded by an advisory lock."""
    async with pool.connection() as conn:
        await conn.execute(read_schema())
    logger.info("Database schema is up to date.")


async def fetch_all(pool: AsyncConnectionPool, query: str, params: tuple = ()) -> List[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchall()


async def fetch_one(pool: AsyncConnectionPool, query: str, params: tuple = ()) -> Optional[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchone()


def sync_connect(retries: int = 10, delay: float = 1.0) -> psycopg.Connection:
    """A synchronous connection for the worker and scripts."""
    for attempt in range(1, retries + 1):
        try:
            return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)
        except psycopg.OperationalError as exc:
            if attempt == retries:
                raise
            logger.warning("Postgres not ready (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def apply_schema_sync(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute(read_schema())


def as_float(value: Any, digits: int = 3) -> float:
    return round(float(value or 0.0), digits)

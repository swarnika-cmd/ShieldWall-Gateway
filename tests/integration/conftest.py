"""Integration fixtures: real Postgres + Redis, in-process gateway, mock upstream on a port.

Needs DATABASE_URL and REDIS_URL (docker-compose.test.yml and the CI
workflow set them).
"""
import os
import threading
import time
import uuid

import httpx
import psycopg
import pytest
import redis
import uvicorn
from psycopg.rows import dict_row

from tests.conftest import MOCK_PORT

pytestmark = pytest.mark.integration

ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]


@pytest.fixture(scope="session")
def mock_upstream():
    """Run the mock provider on a real port in a background thread."""
    from mock_upstream.app import RECEIVED, app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=MOCK_PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("mock upstream did not start")
        time.sleep(0.05)
    yield RECEIVED
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
async def gateway(mock_upstream):
    """An httpx client talking to the gateway app in-process (lifespan included)."""
    import main

    async with main.lifespan(main.app):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://gateway", timeout=30) as client:
            yield client


@pytest.fixture
def pg():
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
        yield conn


@pytest.fixture
def redis_client():
    client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    yield client
    client.close()


@pytest.fixture
def make_project(gateway):
    """Create a project with a fresh key. Depends on `gateway` so the schema exists."""
    from scripts.create_project import create_project

    def _make(budget_usd: float = 100.0):
        name = f"test-{uuid.uuid4().hex[:10]}"
        key = create_project(name, budget_usd)
        return name, key

    return _make


def bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}

import os

import psycopg
import pytest

import db

pytestmark = pytest.mark.integration


async def test_schema_is_idempotent(gateway):
    # The gateway fixture already applied it once at startup; run it twice more.
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        db.apply_schema_sync(conn)
        db.apply_schema_sync(conn)
        cols = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'request_logs'")}
    assert {"gateway_overhead_ms", "upstream_ms", "pii_entities", "relevance_score"} <= cols
    assert "faithfulness" not in cols

"""Failed upstream calls must release the budget hold and be logged."""
import pytest

import budget
import config
from tests.integration.conftest import bearer

pytestmark = pytest.mark.integration


def holds_for(pg, redis_client, name):
    pid = pg.execute("SELECT id FROM projects WHERE name = %s", (name,)).fetchone()["id"]
    spent_key, holds_key, _ = budget.budget_keys(pid)
    return redis_client.hlen(holds_key), int(redis_client.get(spent_key) or 0)


@pytest.mark.parametrize("stream", [False, True])
async def test_unreachable_upstream_releases_hold(gateway, make_project, pg, redis_client, monkeypatch, stream):
    name, key = make_project()
    monkeypatch.setattr(config, "UPSTREAM_URL", "http://127.0.0.1:9/v1/chat/completions")  # closed port
    body = {"model": "gpt-4o-mini", "stream": stream, "messages": [{"role": "user", "content": "hi"}]}
    resp = await gateway.post("/v1/chat/completions", json=body, headers=bearer(key))
    assert resp.status_code == 502
    assert holds_for(pg, redis_client, name) == (0, 0)
    row = pg.execute("SELECT http_status, violations_triggered FROM request_logs WHERE tenant_id = %s",
                     (name,)).fetchone()
    assert row == {"http_status": 502, "violations_triggered": "UPSTREAM_ERROR"}


@pytest.mark.parametrize("stream", [False, True])
async def test_upstream_500_is_passed_through_and_not_charged(gateway, make_project, pg, redis_client, stream):
    name, key = make_project()
    body = {"model": "mock-error-500", "stream": stream, "messages": [{"role": "user", "content": "hi"}]}
    resp = await gateway.post("/v1/chat/completions", json=body, headers=bearer(key))
    assert resp.status_code == 500
    assert holds_for(pg, redis_client, name) == (0, 0)

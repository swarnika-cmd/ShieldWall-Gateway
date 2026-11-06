import asyncio

import pytest

import auth
import budget
import config
import main
from pricing import cost_micro_usd, estimate_input_tokens
from tests.integration.conftest import bearer

pytestmark = pytest.mark.integration

MODEL = "gpt-4o"            # $5 / $15 per 1M tokens
MAX_TOKENS = 100
MESSAGES = [{"role": "user", "content": "Summarise the quarterly report in one line."}]


def estimate_micro() -> int:
    return cost_micro_usd(MODEL, estimate_input_tokens(MESSAGES, MODEL), MAX_TOKENS)


def project_id(pg, name: str) -> int:
    return pg.execute("SELECT id FROM projects WHERE name = %s", (name,)).fetchone()["id"]


async def test_concurrent_requests_never_overspend(gateway, make_project, pg, redis_client, monkeypatch):
    fits = 7
    total = 50
    estimate = estimate_micro()
    # Room for exactly `fits` reservations (plus less than one more).
    budget_micro = fits * estimate + estimate // 2
    name, key = make_project(budget_usd=budget_micro / 1_000_000)
    # Slow upstream so every request reserves before any of them finishes and frees budget.
    monkeypatch.setenv("MOCK_LATENCY_MS", "800")

    body = {"model": MODEL, "messages": MESSAGES, "max_tokens": MAX_TOKENS}
    responses = await asyncio.gather(*[
        gateway.post("/v1/chat/completions", json=body, headers=bearer(key)) for _ in range(total)
    ])
    codes = [r.status_code for r in responses]
    assert codes.count(200) == fits, codes
    assert codes.count(429) == total - fits
    assert all(r.headers.get("X-ShieldWall-Reason") == "budget_exceeded"
               for r in responses if r.status_code == 429)

    spent_key, holds_key, _ = budget.budget_keys(project_id(pg, name))
    spent = int(redis_client.get(spent_key) or 0)
    assert 0 < spent <= budget_micro
    assert redis_client.hlen(holds_key) == 0  # every reservation was reconciled

    rows = pg.execute(
        "SELECT http_status, COUNT(*) AS n, SUM(cost) AS cost FROM request_logs "
        "WHERE tenant_id = %s GROUP BY http_status", (name,)).fetchall()
    by_status = {r["http_status"]: r for r in rows}
    assert by_status[200]["n"] == fits and by_status[429]["n"] == total - fits
    assert float(by_status[200]["cost"]) * 1_000_000 <= budget_micro


async def test_reconcile_frees_unused_reservation(gateway, make_project, redis_client, pg):
    name, key = make_project(budget_usd=1.0)
    body = {"model": MODEL, "messages": MESSAGES, "max_tokens": MAX_TOKENS}
    resp = await gateway.post("/v1/chat/completions", json=body, headers=bearer(key))
    assert resp.status_code == 200
    spent_key, holds_key, _ = budget.budget_keys(project_id(pg, name))
    spent = int(redis_client.get(spent_key))
    assert 0 < spent < estimate_micro()  # charged the real (smaller) cost, not the estimate
    assert redis_client.hlen(holds_key) == 0


async def test_expired_hold_is_swept(gateway, make_project, redis_client, pg):
    """A hold left by a crashed process stops blocking the budget after its TTL."""
    name, key = make_project(budget_usd=estimate_micro() * 1.5 / 1_000_000)
    pid = project_id(pg, name)
    spent_key, holds_key, expiry_key = budget.budget_keys(pid)
    gate = budget.BudgetGate(main.app.state.redis)

    # Simulate a crashed request holding the whole budget, already expired.
    redis_client.hset(holds_key, "crashed", estimate_micro())
    redis_client.zadd(expiry_key, {"crashed": 1})
    res = await gate.reserve(pid, "fresh", int(estimate_micro() * 1.5), estimate_micro())
    assert res.allowed
    assert not redis_client.hexists(holds_key, "crashed")


async def test_redis_down_fails_closed(gateway, make_project, monkeypatch):
    _, key = make_project()
    app_state = main.app.state

    async def broken(*args, **kwargs):
        raise budget.BudgetUnavailable("connection refused")

    monkeypatch.setattr(app_state.budget, "reserve", broken)
    monkeypatch.setattr(config, "BUDGET_FAIL_MODE", "closed")
    body = {"model": MODEL, "messages": MESSAGES}
    resp = await gateway.post("/v1/chat/completions", json=body, headers=bearer(key))
    assert resp.status_code == 503


async def test_auth_cache_avoids_db_after_first_lookup(gateway, make_project, monkeypatch):
    _, key = make_project()
    authn: auth.ProjectAuthenticator = main.app.state.auth
    first = await authn.lookup(auth.hash_api_key(key))

    async def no_db(*args, **kwargs):
        raise AssertionError("cache miss: database was queried")

    monkeypatch.setattr(auth.db, "fetch_one", no_db)
    assert await authn.lookup(auth.hash_api_key(key)) == first


async def test_lua_reserve_vs_naive_check_then_add(redis_client):
    """Shows WHY the check and the reservation must be one atomic step.

    The naive version (what v1 did: read the spend, then later add to it)
    lets every concurrent request see the same old total.
    """
    import redis.asyncio as aioredis

    fits, total, estimate = 5, 40, 100
    budget_micro = fits * estimate
    client = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    try:
        naive_key = "test:naive:spent"
        await client.delete(naive_key)

        async def naive_reserve() -> bool:
            spent = int(await client.get(naive_key) or 0)       # 1. check
            if spent + estimate > budget_micro:
                return False
            await client.incrby(naive_key, estimate)            # 2. record (another request ran in between)
            return True

        naive_allowed = sum(await asyncio.gather(*[naive_reserve() for _ in range(total)]))

        gate = budget.BudgetGate(client)
        pid = 10_000_000 + (hash("lua-vs-naive") % 1000)
        for k in budget.budget_keys(pid):
            await client.delete(k)
        results = await asyncio.gather(*[
            gate.reserve(pid, f"r{i}", budget_micro, estimate) for i in range(total)])
        lua_allowed = sum(r.allowed for r in results)
    finally:
        await client.aclose()

    assert naive_allowed > fits      # the race: overspends
    assert lua_allowed == fits       # atomic: exactly the budget

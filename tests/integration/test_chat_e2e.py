"""End to end: client -> gateway -> mock upstream -> gateway -> client."""
import json

import pytest

from tests.integration.conftest import ADMIN_TOKEN, bearer

pytestmark = pytest.mark.integration

EMAIL_A = "alice.secret@example.com"
EMAIL_B = "bob.private@example.org"
PHONE = "+91 98765 43210"
RAW_VALUES = [EMAIL_A, EMAIL_B, PHONE, "98765 43210"]


def chat_body(stream: bool) -> dict:
    return {
        "model": "gpt-4o-mini",
        "stream": stream,
        "messages": [
            {"role": "system", "content": f"Escalations go to {EMAIL_B}."},
            {"role": "user", "content": f"Contact me at {EMAIL_A} or {PHONE}, cc {EMAIL_B}."},
        ],
    }


def assert_upstream_saw_only_masked(upstream_body: dict):
    text = json.dumps(upstream_body)
    for raw in RAW_VALUES:
        assert raw not in text
    user = upstream_body["messages"][1]["content"]
    assert user == ("Contact me at [REDACTED_EMAIL_2] or [REDACTED_IN_MOBILE_1], "
                    "cc [REDACTED_EMAIL_1].")
    assert upstream_body["messages"][0]["content"] == "Escalations go to [REDACTED_EMAIL_1]."


def assert_no_raw_pii_stored(pg, redis_client, request_id: str):
    row = pg.execute("SELECT * FROM request_logs WHERE request_id = %s", (request_id,)).fetchone()
    assert row is not None, "log row was not written"
    stored = json.dumps(row, default=str)
    for raw in RAW_VALUES:
        assert raw not in stored
    assert row["pii_entities"] == {"EMAIL": 2, "IN_MOBILE": 1}
    assert row["violations_triggered"] == "PII_MASKED"
    assert row["gateway_overhead_ms"] is not None and row["upstream_ms"] is not None
    # Nothing in Redis holds the raw values either.
    for key in redis_client.scan_iter("*"):
        kind = redis_client.type(key)
        if kind == "string":
            dump = redis_client.get(key) or ""
        elif kind == "hash":
            dump = json.dumps(redis_client.hgetall(key))
        elif kind == "list":
            dump = json.dumps(redis_client.lrange(key, 0, -1))
        elif kind == "zset":
            dump = json.dumps(redis_client.zrange(key, 0, -1))
        else:
            dump = ""
        for raw in RAW_VALUES:
            assert raw not in dump, f"raw PII found in redis key {key}"


async def test_non_streaming_masks_upstream_and_unmasks_client(gateway, make_project, mock_upstream,
                                                               pg, redis_client):
    _, key = make_project()
    resp = await gateway.post("/v1/chat/completions", json=chat_body(False), headers=bearer(key))
    assert resp.status_code == 200, resp.text

    assert_upstream_saw_only_masked(mock_upstream[-1]["body"])
    answer = resp.json()["choices"][0]["message"]["content"]
    assert answer == f"You said: Contact me at {EMAIL_A} or {PHONE}, cc {EMAIL_B}."

    assert_no_raw_pii_stored(pg, redis_client, resp.headers["X-ShieldWall-Request-Id"])


async def test_streaming_masks_upstream_and_unmasks_client(gateway, make_project, mock_upstream,
                                                           pg, redis_client):
    _, key = make_project()
    resp = await gateway.post("/v1/chat/completions", json=chat_body(True), headers=bearer(key))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")

    body = mock_upstream[-1]["body"]
    assert_upstream_saw_only_masked(body)
    assert body["stream_options"] == {"include_usage": True}

    text, saw_done = "", False
    for line in resp.text.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            saw_done = True
            continue
        for choice in json.loads(data).get("choices", []):
            text += choice.get("delta", {}).get("content") or ""
    assert saw_done
    assert text == f"You said: Contact me at {EMAIL_A} or {PHONE}, cc {EMAIL_B}."
    assert "REDACTED" not in resp.text

    assert_no_raw_pii_stored(pg, redis_client, resp.headers["X-ShieldWall-Request-Id"])


async def test_security_logs_show_entity_counts_not_values(gateway, make_project):
    name, key = make_project()
    resp = await gateway.post("/v1/chat/completions", json=chat_body(False), headers=bearer(key))
    assert resp.status_code == 200
    logs = (await gateway.get("/api/security/logs", headers=bearer(ADMIN_TOKEN))).json()
    mine = [entry for entry in logs if entry["tenant_id"] == name]
    assert mine and mine[0]["pii_entities"] == {"EMAIL": 2, "IN_MOBILE": 1}
    assert "pii_mappings" not in mine[0]
    dump = json.dumps(logs)
    for raw in RAW_VALUES:
        assert raw not in dump


async def test_summary_reports_overhead_and_upstream_separately(gateway, make_project):
    _, key = make_project()
    await gateway.post("/v1/chat/completions", json=chat_body(False), headers=bearer(key))
    summary = (await gateway.get("/api/analytics/summary?window=1h", headers=bearer(ADMIN_TOKEN))).json()
    assert summary["requests"] >= 1
    # The mock sleeps MOCK_LATENCY_MS (20 ms in tests); that wait is upstream time, not overhead.
    assert summary["upstream_ms_p50"] >= 15
    assert summary["gateway_overhead_ms_p50"] < summary["upstream_ms_p50"]
    assert "avg_overhead_ms" not in summary

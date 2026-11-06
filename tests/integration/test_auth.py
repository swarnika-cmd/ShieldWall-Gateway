import pytest

from tests.integration.conftest import ADMIN_TOKEN, bearer

pytestmark = pytest.mark.integration

CHAT = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}


async def test_no_key_is_rejected_and_upstream_not_called(gateway, mock_upstream):
    before = len(mock_upstream)
    resp = await gateway.post("/v1/chat/completions", json=CHAT)
    assert resp.status_code == 401
    assert len(mock_upstream) == before


@pytest.mark.parametrize("header", [
    "Bearer sw_not-a-real-key",
    "Bearer sk-someone-elses-openai-key",
    "Basic dXNlcjpwYXNz",
    "Bearer ",
])
async def test_bad_keys_are_rejected(gateway, header):
    resp = await gateway.post("/v1/chat/completions", json=CHAT, headers={"Authorization": header})
    assert resp.status_code == 401


async def test_old_x_project_id_header_is_not_enough(gateway):
    resp = await gateway.post("/v1/chat/completions", json=CHAT, headers={"X-Project-ID": "anything"})
    assert resp.status_code == 401


async def test_valid_key_uses_gateway_provider_key_upstream(gateway, make_project, mock_upstream):
    _, key = make_project()
    resp = await gateway.post("/v1/chat/completions", json=CHAT, headers=bearer(key))
    assert resp.status_code == 200
    # The client's sw_ key is never forwarded; the gateway's own provider key is used.
    assert mock_upstream[-1]["authorization"] == "Bearer test-upstream-key"


@pytest.mark.parametrize("path", [
    "/api/analytics", "/api/analytics/tenants", "/api/analytics/summary", "/api/security/logs",
])
async def test_admin_endpoints_require_admin_token(gateway, make_project, path):
    _, project_key = make_project()
    assert (await gateway.get(path)).status_code == 401
    assert (await gateway.get(path, headers=bearer("wrong-token"))).status_code == 401
    # A project key is not an admin token.
    assert (await gateway.get(path, headers=bearer(project_key))).status_code == 401
    assert (await gateway.get(path, headers=bearer(ADMIN_TOKEN))).status_code == 200


async def test_admin_window_is_validated(gateway):
    resp = await gateway.get("/api/analytics?window=999y", headers=bearer(ADMIN_TOKEN))
    assert resp.status_code == 400

"""The provider connection pool is built from the configured limits (httpcore pool attributes)."""
import pytest

import config
import main

pytestmark = pytest.mark.integration


def pool_limits(client):
    pool = client._transport._pool   # httpcore.AsyncConnectionPool behind httpx's default transport
    return pool._max_connections, pool._max_keepalive_connections


async def test_gateway_pool_uses_default_limits(gateway):
    assert pool_limits(main.app.state.http) == (config.UPSTREAM_MAX_CONNECTIONS, config.UPSTREAM_MAX_KEEPALIVE)


async def test_gateway_pool_follows_configured_limits(monkeypatch, mock_upstream):
    monkeypatch.setattr(config, "UPSTREAM_MAX_CONNECTIONS", 123)
    monkeypatch.setattr(config, "UPSTREAM_MAX_KEEPALIVE", 45)
    async with main.lifespan(main.app):
        assert pool_limits(main.app.state.http) == (123, 45)

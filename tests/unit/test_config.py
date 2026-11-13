import importlib

import config


def reload_config():
    return importlib.reload(config)


def test_upstream_pool_defaults(monkeypatch):
    monkeypatch.delenv("UPSTREAM_MAX_CONNECTIONS", raising=False)
    monkeypatch.delenv("UPSTREAM_MAX_KEEPALIVE", raising=False)
    try:
        cfg = reload_config()
        assert (cfg.UPSTREAM_MAX_CONNECTIONS, cfg.UPSTREAM_MAX_KEEPALIVE) == (500, 100)
    finally:
        monkeypatch.undo()
        reload_config()


def test_upstream_pool_from_env(monkeypatch):
    monkeypatch.setenv("UPSTREAM_MAX_CONNECTIONS", "250")
    monkeypatch.setenv("UPSTREAM_MAX_KEEPALIVE", "50")
    try:
        cfg = reload_config()
        assert (cfg.UPSTREAM_MAX_CONNECTIONS, cfg.UPSTREAM_MAX_KEEPALIVE) == (250, 50)
    finally:
        monkeypatch.undo()
        reload_config()

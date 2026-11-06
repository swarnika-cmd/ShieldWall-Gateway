"""Test settings. They must be set before any gateway module is imported."""
import os

MOCK_PORT = int(os.getenv("MOCK_PORT", "18210"))

os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")  # log tasks run inline
os.environ.setdefault("UPSTREAM_URL", f"http://127.0.0.1:{MOCK_PORT}/v1/chat/completions")
os.environ.setdefault("UPSTREAM_API_KEY", "test-upstream-key")
os.environ.setdefault("MOCK_LATENCY_MS", "20")
os.environ.setdefault("LOG_LEVEL", "WARNING")

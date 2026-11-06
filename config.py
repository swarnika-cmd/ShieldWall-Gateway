"""All runtime settings, read once from environment variables.

Keeping them in one place makes it easy to see what can be configured
and what the defaults are.
"""
import os


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/shieldwall")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Size of the async Postgres pool used by the API process. The hot path never
# touches Postgres except for API-key lookups on a cache miss, so a small pool
# is enough (see docs in README "Database").
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

# Upstream provider. The gateway attaches its OWN provider key, and only for
# requests that were authenticated with a valid project key.
_default_upstream = "https://api.openai.com/v1/chat/completions"
if os.getenv("GROQ_API_KEY"):
    _default_upstream = "https://api.groq.com/openai/v1/chat/completions"
UPSTREAM_URL = os.getenv("UPSTREAM_URL", _default_upstream)
UPSTREAM_API_KEY = (
    os.getenv("UPSTREAM_API_KEY")
    or os.getenv("GROQ_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ""
)
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "60"))
UPSTREAM_PROVIDER_NAME = os.getenv("UPSTREAM_PROVIDER_NAME", "openai-compatible")

# Admin API (/api/*). If ADMIN_TOKEN is empty the admin API is disabled.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# How long a validated project key stays in the in-process cache.
AUTH_CACHE_TTL_SECONDS = float(os.getenv("AUTH_CACHE_TTL_SECONDS", "60"))

# Budget enforcement.
# If the client does not send max_tokens we set this value, so the cost
# estimate we reserve is a real upper bound on output tokens.
DEFAULT_MAX_OUTPUT_TOKENS = int(os.getenv("DEFAULT_MAX_OUTPUT_TOKENS", "1024"))
# A reservation that is never reconciled (process crashed mid-request) is
# dropped after this many seconds so it does not block the budget forever.
RESERVATION_TTL_SECONDS = int(os.getenv("RESERVATION_TTL_SECONDS", "600"))
# What to do when Redis is unreachable: "closed" rejects requests with 503
# (default, because without Redis we cannot enforce budgets); "open" lets
# requests through without budget enforcement.
BUDGET_FAIL_MODE = os.getenv("BUDGET_FAIL_MODE", "closed")

# Optional retrieval-relevance scoring in the Celery worker (needs the extra
# packages in requirements-eval.txt). Disabled by default.
ENABLE_RELEVANCE_EVAL = _env_bool("ENABLE_RELEVANCE_EVAL", False)
RELEVANCE_ALERT_THRESHOLD = float(os.getenv("RELEVANCE_ALERT_THRESHOLD", "0.5"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

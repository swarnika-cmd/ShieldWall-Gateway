"""Project API keys and the admin token.

Project keys look like  sw_<43 random url-safe characters>.
Only sha256(key) is stored in Postgres. Because the key has 256 bits of
randomness, a plain fast hash is enough (no bcrypt needed): nobody can
brute-force a 256-bit secret, and a fast hash keeps the lookup cheap.
"""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

import config
import db

KEY_PREFIX = "sw_"


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    monthly_budget_micro: int


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


class ProjectAuthenticator:
    """Looks up a project by key hash, with a small in-process TTL cache."""

    def __init__(self, pool, ttl_seconds: float = None) -> None:
        self.pool = pool
        self.ttl = config.AUTH_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        self._cache: Dict[str, Tuple[float, Project]] = {}

    async def lookup(self, key_hash: str) -> Optional[Project]:
        cached = self._cache.get(key_hash)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        row = await db.fetch_one(
            self.pool,
            "SELECT id, name, monthly_budget_usd FROM projects WHERE api_key_hash = %s",
            (key_hash,),
        )
        if row is None:
            # Misses are not cached, so a newly created key works immediately.
            return None
        project = Project(
            id=row["id"],
            name=row["name"],
            monthly_budget_micro=int(row["monthly_budget_usd"] * 1_000_000),
        )
        self._cache[key_hash] = (time.monotonic() + self.ttl, project)
        return project

    async def authenticate(self, request: Request) -> Project:
        token = _bearer_token(request)
        if not token or not token.startswith(KEY_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or malformed project API key. Send 'Authorization: Bearer sw_...'.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            project = await self.lookup(hash_api_key(token))
        except Exception as exc:
            # Postgres down and key not cached: fail closed, but say why.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Key store unavailable.") from exc
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid project API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return project


def require_admin(request: Request) -> None:
    """FastAPI dependency protecting every /api/* route."""
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API disabled: set ADMIN_TOKEN on the server.",
        )
    token = _bearer_token(request) or ""
    # compare_digest takes the same time whether the first or last character
    # differs, so the token cannot be guessed one character at a time.
    if not hmac.compare_digest(token.encode("utf-8"), config.ADMIN_TOKEN.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

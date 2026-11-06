"""Admin / dashboard API. Every route here requires the ADMIN_TOKEN.

All queries are bounded by a time window so they use idx_logs_time_covering
(see docs/db-indexing.md) instead of scanning the whole table.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import config
import db
from auth import require_admin

logger = logging.getLogger("shieldwall.admin")

router = APIRouter(prefix="/api", tags=["Admin"], dependencies=[Depends(require_admin)])

WINDOWS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def window_start(window: str) -> datetime:
    if window not in WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {sorted(WINDOWS)}")
    return datetime.now(timezone.utc) - WINDOWS[window]


@router.get("/analytics", summary="Cost, latency and relevance for a time window")
async def analytics(request: Request, window: str = "24h"):
    row = await db.fetch_one(
        request.app.state.pool,
        """
        SELECT COUNT(*)                                                   AS requests,
               COALESCE(SUM(cost), 0)                                     AS total_cost,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)   AS p95_latency_ms,
               AVG(relevance_score)                                       AS avg_relevance_score
        FROM request_logs
        WHERE timestamp >= %s
        """,
        (window_start(window),),
    )
    return {
        "window": window,
        "requests": row["requests"],
        "total_cost": db.as_float(row["total_cost"], 6),
        "p95_latency_ms": db.as_float(row["p95_latency_ms"], 1),
        "avg_relevance_score": (None if row["avg_relevance_score"] is None
                                else db.as_float(row["avg_relevance_score"], 3)),
    }


@router.get("/analytics/tenants", summary="Spend per project for a time window")
async def tenant_spend(request: Request, window: str = "24h"):
    rows = await db.fetch_all(
        request.app.state.pool,
        """
        SELECT tenant_id, SUM(cost) AS total_cost
        FROM request_logs
        WHERE timestamp >= %s
        GROUP BY tenant_id
        ORDER BY total_cost DESC
        """,
        (window_start(window),),
    )
    return [{"tenant_id": r["tenant_id"], "total_cost": db.as_float(r["total_cost"], 6)} for r in rows]


@router.get("/analytics/summary", summary="Headline numbers, including gateway overhead")
async def summary(request: Request, window: str = "24h"):
    row = await db.fetch_one(
        request.app.state.pool,
        """
        SELECT COUNT(*)                                                         AS requests,
               COALESCE(SUM(cost), 0)                                           AS total_spend,
               COUNT(*) FILTER (WHERE violations_triggered = 'BUDGET_EXCEEDED') AS blocked_requests,
               -- latency figures only for requests that were forwarded upstream
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY gateway_overhead_ms)
                   FILTER (WHERE upstream_ms IS NOT NULL)                        AS overhead_p50,
               percentile_cont(0.99) WITHIN GROUP (ORDER BY gateway_overhead_ms)
                   FILTER (WHERE upstream_ms IS NOT NULL)                        AS overhead_p99,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY upstream_ms)         AS upstream_p50
        FROM request_logs
        WHERE timestamp >= %s
        """,
        (window_start(window),),
    )
    return {
        "window": window,
        "requests": row["requests"],
        "total_spend": db.as_float(row["total_spend"], 6),
        "blocked_requests": row["blocked_requests"],
        # Time spent inside the gateway, NOT counting the wait for the provider.
        "gateway_overhead_ms_p50": db.as_float(row["overhead_p50"], 3),
        "gateway_overhead_ms_p99": db.as_float(row["overhead_p99"], 3),
        # Time spent waiting for the provider.
        "upstream_ms_p50": db.as_float(row["upstream_p50"], 1),
    }


@router.get("/security/logs", summary="Recent requests with a violation (no raw PII)")
async def security_logs(request: Request, window: str = "24h",
                        limit: int = Query(default=100, ge=1, le=500)):
    rows = await db.fetch_all(
        request.app.state.pool,
        """
        SELECT request_id, tenant_id, EXTRACT(EPOCH FROM timestamp) AS ts, model,
               latency_ms, http_status, violations_triggered, pii_entities
        FROM request_logs
        WHERE violations_triggered IS NOT NULL AND violations_triggered <> ''
          AND timestamp >= %s
        ORDER BY timestamp DESC
        LIMIT %s
        """,
        (window_start(window), limit),
    )
    return [
        {
            "request_id": r["request_id"],
            "tenant_id": r["tenant_id"],
            "timestamp": float(r["ts"]),
            "model": r["model"],
            "latency_ms": r["latency_ms"],
            "http_status": r["http_status"],
            "violations_triggered": r["violations_triggered"],
            # Entity types and counts only, e.g. {"EMAIL": 1}. Values are never stored.
            "pii_entities": r["pii_entities"] or {},
        }
        for r in rows
    ]


async def relevance_alert_loop(pool, interval_seconds: float = 60.0, cooldown_seconds: float = 600.0):
    """Log a warning when average retrieval relevance drops (only if eval is enabled)."""
    last_alert = 0.0
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            row = await db.fetch_one(
                pool,
                """
                SELECT COUNT(relevance_score) AS n, AVG(relevance_score) AS avg_score
                FROM request_logs WHERE timestamp >= NOW() - INTERVAL '10 minutes'
                """,
            )
            if row["n"] and float(row["avg_score"]) < config.RELEVANCE_ALERT_THRESHOLD:
                if loop.time() - last_alert > cooldown_seconds:
                    last_alert = loop.time()
                    logger.warning("[ALERT] avg retrieval relevance %.3f < %.2f over %d requests (10 min)",
                                   float(row["avg_score"]), config.RELEVANCE_ALERT_THRESHOLD, row["n"])
        except Exception as exc:
            logger.error("Relevance alert loop error: %s", exc)

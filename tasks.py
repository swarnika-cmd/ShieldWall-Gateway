"""Celery worker: writes request logs to Postgres off the hot path.

Each worker process (or thread, with --pool=threads or eager mode in tests)
keeps ONE synchronous psycopg connection of its own; connections are never
shared between processes or threads. The schema
is created by the API at startup, not here.

Optional: retrieval-relevance scoring with a cross-encoder
(ENABLE_RELEVANCE_EVAL=true, needs requirements-eval.txt). The model
cross-encoder/ms-marco-MiniLM-L-6-v2 is trained to score how relevant a
passage is to a search query. We use it for exactly that: how relevant the
retrieved RAG chunks are to the user's question. It does NOT measure whether
the answer is faithful to the context, so we do not call it that.
"""
import json
import logging
import math
import os
import threading
from typing import List, Optional

import psycopg
from celery import Celery

import config
import db

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger("shieldwall.worker")

celery_app = Celery("shieldwall", broker=config.REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    timezone="UTC",
    enable_utc=True,
    # Tests set this so tasks run inline without a worker process.
    task_always_eager=os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true",
    # If Redis is down, fail fast instead of blocking the API thread for seconds.
    task_publish_retry_policy={"max_retries": 1, "interval_start": 0, "interval_step": 0.2},
)

_local = threading.local()


def get_connection() -> psycopg.Connection:
    """One lazily-opened connection per process/thread; reopened if it broke."""
    conn: Optional[psycopg.Connection] = getattr(_local, "conn", None)
    if conn is None or conn.closed or conn.broken:
        conn = _local.conn = db.sync_connect()
    return conn


INSERT_LOG_SQL = """
INSERT INTO request_logs (
    request_id, tenant_id, timestamp, model, upstream_provider,
    latency_ms, upstream_ms, gateway_overhead_ms, http_status,
    input_tokens, output_tokens, cost, violations_triggered, pii_entities
) VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (request_id) DO NOTHING
"""


@celery_app.task(name="tasks.log_request")
def log_request(payload: dict) -> str:
    """Persist one request log row. The payload never contains raw PII."""
    conn = get_connection()
    with conn.transaction():
        conn.execute(
            INSERT_LOG_SQL,
            (
                payload["request_id"],
                payload["tenant_id"],
                payload["timestamp"],
                payload["model"],
                payload["upstream_provider"],
                payload["latency_ms"],
                payload.get("upstream_ms"),
                payload.get("gateway_overhead_ms"),
                payload["http_status"],
                payload["input_tokens"],
                payload["output_tokens"],
                payload["cost_usd"],
                payload.get("violations_triggered", ""),
                json.dumps(payload.get("pii_entities") or {}),
            ),
        )

    if config.ENABLE_RELEVANCE_EVAL and payload.get("user_query") and payload.get("rag_context"):
        score_relevance.delay(payload["request_id"], payload["user_query"], payload["rag_context"])
    return payload["request_id"]


_cross_encoder = None


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def relevance_score(user_query: str, chunks: List[str]) -> float:
    """Mean query-to-chunk relevance in [0, 1] from the ms-marco cross-encoder."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder  # only installed with requirements-eval.txt
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    logits = _cross_encoder.predict([(user_query, chunk) for chunk in chunks])
    scores = [_sigmoid(float(x)) for x in list(logits)]
    return round(sum(scores) / len(scores), 3)


@celery_app.task(name="tasks.score_relevance")
def score_relevance(request_id: str, user_query: str, rag_context: List[str]) -> str:
    score = relevance_score(user_query, rag_context)
    conn = get_connection()
    with conn.transaction():
        conn.execute("UPDATE request_logs SET relevance_score = %s WHERE request_id = %s",
                     (score, request_id))
    logger.info("relevance_score=%.3f for %s", score, request_id)
    return request_id

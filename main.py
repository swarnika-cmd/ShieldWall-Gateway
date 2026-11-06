"""ShieldWall gateway: an OpenAI-compatible proxy in front of an LLM provider.

Hot path for POST /v1/chat/completions (see README for the diagram):
  1. authenticate the project API key           (auth.py)
  2. mask PII in the prompt                      (pii.py)
  3. reserve the worst-case cost in Redis (Lua)  (budget.py)
  4. call the upstream provider with OUR key
  5. unmask placeholders in the answer (also for streams)  (streaming.py)
  6. after the response: reconcile the real cost and queue a log row
     for the Celery worker                       (tasks.py)
"""
import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, List, Optional

import anyio
import httpx
import redis.asyncio as aioredis
from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

import admin_api
import config
import db
from auth import Project, ProjectAuthenticator
from budget import BudgetGate, BudgetUnavailable, Reservation
from pii import PiiMasker
from pricing import cost_micro_usd, count_text_tokens, estimate_input_tokens, micro_to_usd
from streaming import SseUnmaskRelay, sse

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger("shieldwall")


class ChatMessage(BaseModel):
    role: str = Field(..., description="system, user or assistant")
    content: Any = Field(..., description="A string, or a list of content parts")


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # other OpenAI fields are forwarded as-is

    model: str = Field(default="gpt-4o-mini")
    messages: List[ChatMessage]
    stream: bool = False
    user_query: Optional[str] = Field(default=None, description="Optional, for relevance scoring")
    rag_context: Optional[List[str]] = Field(default=None, description="Optional, for relevance scoring")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await db.create_pool()
    await db.apply_schema(pool)  # idempotent migration on every start
    # Load tokenizer vocabularies now (~100 ms each) instead of on the first request.
    await asyncio.to_thread(count_text_tokens, "warm up", "gpt-4o-mini")
    await asyncio.to_thread(count_text_tokens, "warm up", "gpt-4")

    redis_client = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    try:
        await redis_client.ping()
    except Exception as exc:
        # Not fatal: requests get 503 (BUDGET_FAIL_MODE=closed) until Redis is back.
        logger.error("Redis not reachable at startup: %s", exc)

    app.state.pool = pool
    app.state.redis = redis_client
    app.state.auth = ProjectAuthenticator(pool)
    app.state.budget = BudgetGate(redis_client)
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(config.UPSTREAM_TIMEOUT_SECONDS, connect=5.0),
        limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
    )
    alert_task = None
    if config.ENABLE_RELEVANCE_EVAL:
        alert_task = asyncio.create_task(admin_api.relevance_alert_loop(pool))

    yield

    if alert_task:
        alert_task.cancel()
    await app.state.http.aclose()
    await redis_client.aclose()
    await pool.close()


app = FastAPI(title="ShieldWall Gateway", version="2.0.0", lifespan=lifespan)
app.include_router(admin_api.router)


@dataclass
class RequestContext:
    """Everything we need to finish (reconcile + log) one request."""
    project: Project
    request_id: str
    model: str
    masker: PiiMasker
    reservation: Optional[Reservation]
    estimated_input_tokens: int
    started: float
    user_query: Optional[str] = None
    rag_context: Optional[List[str]] = None
    upstream_seconds: float = 0.0   # time spent waiting for the provider
    client_seconds: float = 0.0     # time spent waiting to send stream chunks to the client
    total_seconds: Optional[float] = None

    def stop_clock(self) -> None:
        if self.total_seconds is None:
            self.total_seconds = time.perf_counter() - self.started

    def overhead_ms(self) -> float:
        self.stop_clock()
        return max(0.0, (self.total_seconds - self.upstream_seconds - self.client_seconds) * 1000)


def enqueue_log(payload: dict) -> None:
    """Hand the log row to Celery (runs in a worker thread, see finish_request)."""
    from tasks import log_request
    try:
        log_request.delay(payload)
    except Exception as exc:
        logger.error("Could not enqueue request log: %s", exc)


async def finish_request(app: FastAPI, ctx: RequestContext, http_status: int,
                         usage: Optional[dict], masked_response: str, violation: str = "") -> None:
    """Reconcile the budget with the real cost and queue the log row."""
    prompt_tokens = ctx.estimated_input_tokens
    completion_tokens = 0
    if usage:
        prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
        completion_tokens = usage.get("completion_tokens", 0)
    elif masked_response:
        completion_tokens = count_text_tokens(masked_response, ctx.model)
    charged = http_status == 200 or bool(masked_response)
    actual_micro = cost_micro_usd(ctx.model, prompt_tokens, completion_tokens) if charged else 0

    if ctx.reservation is not None:
        try:
            await app.state.budget.reconcile(ctx.project.id, ctx.request_id, actual_micro,
                                             ctx.reservation.reserved_at)
        except Exception as exc:
            # The hold expires on its own after RESERVATION_TTL_SECONDS.
            logger.error("Budget reconcile failed for %s: %s", ctx.request_id, exc)

    entities = ctx.masker.entity_counts()
    if not violation and entities:
        violation = "PII_MASKED"
    payload = {
        "request_id": ctx.request_id,
        "tenant_id": ctx.project.name,
        "timestamp": time.time(),
        "model": ctx.model,
        "upstream_provider": config.UPSTREAM_PROVIDER_NAME,
        "latency_ms": int((ctx.total_seconds or 0) * 1000),
        # None when the request never reached the provider (e.g. blocked by budget).
        "upstream_ms": round(ctx.upstream_seconds * 1000, 3) if ctx.upstream_seconds else None,
        "gateway_overhead_ms": round(ctx.overhead_ms(), 3),
        "http_status": http_status,
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "cost_usd": micro_to_usd(actual_micro),
        "violations_triggered": violation,
        "pii_entities": entities,  # counts only, never values
    }
    if config.ENABLE_RELEVANCE_EVAL and ctx.user_query and ctx.rag_context:
        # The worker only ever sees masked text.
        payload["user_query"] = ctx.masker.mask(ctx.user_query)
        payload["rag_context"] = [ctx.masker.mask(chunk) for chunk in ctx.rag_context]
    await asyncio.to_thread(enqueue_log, payload)


def upstream_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if config.UPSTREAM_API_KEY:
        headers["Authorization"] = f"Bearer {config.UPSTREAM_API_KEY}"
    return headers


async def proxy_non_streaming(app: FastAPI, ctx: RequestContext, body: dict,
                              background_tasks: BackgroundTasks) -> Response:
    sent_at = time.perf_counter()
    try:
        upstream = await app.state.http.post(config.UPSTREAM_URL, json=body, headers=upstream_headers())
    except httpx.HTTPError as exc:
        ctx.upstream_seconds += time.perf_counter() - sent_at
        ctx.stop_clock()
        logger.error("Upstream request failed: %s", exc)
        # Return (not raise) so the background task that releases the budget hold still runs.
        background_tasks.add_task(finish_request, app, ctx, 502, None, "", "UPSTREAM_ERROR")
        return JSONResponse({"detail": "Upstream provider unreachable."}, status_code=502)
    ctx.upstream_seconds += time.perf_counter() - sent_at

    headers = {"X-ShieldWall-Request-Id": ctx.request_id}
    try:
        data = upstream.json()
    except ValueError:
        data = None

    if upstream.status_code != 200 or not isinstance(data, dict):
        ctx.stop_clock()
        background_tasks.add_task(finish_request, app, ctx, upstream.status_code, None, "", "UPSTREAM_ERROR")
        # A 401/403 from the provider is OUR key's problem, not the client's.
        code = 502 if upstream.status_code in (401, 403) or data is None else upstream.status_code
        return JSONResponse({"detail": "Upstream provider error.", "upstream_status": upstream.status_code},
                            status_code=code, headers=headers)

    masked_response = ""
    for choice in data.get("choices") or []:
        message = choice.get("message") or {}
        if isinstance(message.get("content"), str):
            masked_response += message["content"]
            message["content"] = ctx.masker.unmask(message["content"])

    response = JSONResponse(data, headers=headers)  # body is serialised here
    ctx.stop_clock()
    background_tasks.add_task(finish_request, app, ctx, 200, data.get("usage"), masked_response)
    return response


async def proxy_streaming(app: FastAPI, ctx: RequestContext, body: dict,
                          background_tasks: BackgroundTasks) -> Response:
    client: httpx.AsyncClient = app.state.http
    sent_at = time.perf_counter()
    try:
        upstream = await client.send(
            client.build_request("POST", config.UPSTREAM_URL, json=body, headers=upstream_headers()),
            stream=True,
        )
    except httpx.HTTPError as exc:
        ctx.upstream_seconds += time.perf_counter() - sent_at
        ctx.stop_clock()
        logger.error("Upstream stream failed to start: %s", exc)
        background_tasks.add_task(finish_request, app, ctx, 502, None, "", "UPSTREAM_ERROR")
        return JSONResponse({"detail": "Upstream provider unreachable."}, status_code=502)
    ctx.upstream_seconds += time.perf_counter() - sent_at

    # Check the status BEFORE we start streaming, so errors keep their status code.
    if upstream.status_code != 200:
        await upstream.aread()
        await upstream.aclose()
        ctx.stop_clock()
        background_tasks.add_task(finish_request, app, ctx, upstream.status_code, None, "", "UPSTREAM_ERROR")
        code = 502 if upstream.status_code in (401, 403) else upstream.status_code
        return JSONResponse({"detail": "Upstream provider error.", "upstream_status": upstream.status_code},
                            status_code=code)

    async def relay():
        relay = SseUnmaskRelay(ctx.masker.mappings)
        http_status = 200
        lines = upstream.aiter_lines()
        try:
            while not relay.done:
                wait_start = time.perf_counter()
                try:
                    line = await lines.__anext__()
                except StopAsyncIteration:
                    break  # upstream closed without [DONE]
                except httpx.HTTPError as exc:
                    logger.warning("Upstream stream broke for %s: %s", ctx.request_id, exc)
                    http_status = 502
                    break
                finally:
                    ctx.upstream_seconds += time.perf_counter() - wait_start

                for event in relay.process_line(line):
                    send_start = time.perf_counter()
                    yield event
                    ctx.client_seconds += time.perf_counter() - send_start

            # Never drop text that was held back waiting for a placeholder to complete.
            for event in relay.finish():
                yield event
            if http_status != 200:
                yield sse('{"error": {"message": "upstream stream interrupted"}}')
        finally:
            ctx.stop_clock()
            # Shield the clean-up from cancellation (client disconnects) so the
            # budget hold is always reconciled.
            with anyio.CancelScope(shield=True):
                await upstream.aclose()
                await finish_request(app, ctx, http_status, relay.usage, relay.masked_text(),
                                     "UPSTREAM_ERROR" if http_status != 200 else "")

    return StreamingResponse(relay(), media_type="text/event-stream",
                             headers={"X-ShieldWall-Request-Id": ctx.request_id})


@app.post("/v1/chat/completions", tags=["Gateway"], summary="OpenAI-compatible chat completion")
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ChatCompletionRequest = Body(..., examples=[{
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": "My email is test@example.com"}],
    }]),
):
    started = time.perf_counter()
    app_ = request.app

    # 1. Who is calling? (401 if no valid project key)
    project = await app_.state.auth.authenticate(request)

    body_dict = body.model_dump(exclude_none=True)
    user_query = body_dict.pop("user_query", None)
    rag_context = body_dict.pop("rag_context", None)
    model = body_dict["model"]
    request_id = f"req_{uuid.uuid4().hex}"

    # 2. Mask PII. One masker for ALL messages, so placeholders never collide.
    masker = PiiMasker()
    body_dict["messages"] = masker.mask_messages(body_dict["messages"])

    # 3. Reserve the worst-case cost. We cap output tokens so the estimate is an upper bound.
    max_output = body_dict.get("max_tokens") or body_dict.get("max_completion_tokens")
    if not max_output:
        max_output = body_dict["max_tokens"] = config.DEFAULT_MAX_OUTPUT_TOKENS
    input_tokens = estimate_input_tokens(body_dict["messages"], model)
    estimate_micro = cost_micro_usd(model, input_tokens, max_output)

    reservation: Optional[Reservation] = None
    try:
        reservation = await app_.state.budget.reserve(
            project.id, request_id, project.monthly_budget_micro, estimate_micro)
    except BudgetUnavailable as exc:
        if config.BUDGET_FAIL_MODE != "open":
            raise HTTPException(status_code=503, detail="Budget store unavailable; request rejected.",
                                headers={"X-ShieldWall-Reason": "budget_store_unavailable"}) from exc
        logger.warning("Redis down, BUDGET_FAIL_MODE=open: %s passes without a budget check (%s)",
                       request_id, exc)

    ctx = RequestContext(project, request_id, model, masker, reservation, input_tokens, started,
                         user_query, rag_context)

    if reservation is not None and not reservation.allowed:
        ctx.reservation = None  # nothing to reconcile
        ctx.stop_clock()
        background_tasks.add_task(finish_request, app_, ctx, 429, None, "", "BUDGET_EXCEEDED")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Monthly project budget exceeded.",
                     "budget_usd": micro_to_usd(project.monthly_budget_micro),
                     "spent_usd": micro_to_usd(reservation.spent_micro),
                     "reserved_usd": micro_to_usd(reservation.reserved_micro)},
            headers={"X-ShieldWall-Reason": "budget_exceeded", "X-ShieldWall-Request-Id": request_id},
        )

    if body_dict.get("stream"):
        body_dict.setdefault("stream_options", {})["include_usage"] = True
        return await proxy_streaming(app_, ctx, body_dict, background_tasks)
    return await proxy_non_streaming(app_, ctx, body_dict, background_tasks)


@app.get("/health", tags=["System"])
async def health(request: Request):
    result = {"status": "ok", "redis": "ok", "postgres": "ok"}
    try:
        await request.app.state.redis.ping()
    except Exception:
        result["redis"] = "down"
    try:
        await db.fetch_one(request.app.state.pool, "SELECT 1 AS ok")
    except Exception:
        result["postgres"] = "down"
    if "down" in result.values():
        result["status"] = "degraded"
    return result


# Serve the built admin dashboard (dashboard/dist) at "/" if present.
_dashboard_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "dist")
if os.path.isdir(_dashboard_dist):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_dashboard_dist, html=True), name="dashboard")

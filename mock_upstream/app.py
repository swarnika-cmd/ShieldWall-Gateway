"""A fake OpenAI-compatible provider for tests, local demos and benchmarks.

POST /v1/chat/completions
  * waits MOCK_LATENCY_MS (default 200) to simulate model latency
  * replies with "You said: <last user message>", i.e. it echoes the text
    it received. Because the gateway masks PII before forwarding, the echo
    contains placeholders, which lets tests check that the gateway unmasks
    them on the way back.
  * stream=true returns SSE chunks of MOCK_CHUNK_CHARS characters, so
    placeholders get split across chunks.

Every request body is kept in RECEIVED (last 1000) so in-process tests can
check exactly what the provider saw. GET /_received returns it too.
"""
import asyncio
import json
import os
import time
import uuid
from collections import deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock LLM upstream")
RECEIVED: deque = deque(maxlen=1000)


def latency_seconds() -> float:
    return float(os.getenv("MOCK_LATENCY_MS", "200")) / 1000


def chunk_chars() -> int:
    return int(os.getenv("MOCK_CHUNK_CHARS", "5"))


def _text_of(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


def _rough_tokens(text: str) -> int:
    # Deliberately low (word count) so the gateway's tiktoken-based estimate
    # is always an upper bound in tests.
    return len(text.split())


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    RECEIVED.append({"body": body, "authorization": request.headers.get("authorization")})

    messages = body.get("messages", [])
    user_messages = [m for m in messages if m.get("role") == "user"]
    prompt_text = " ".join(_text_of(m) for m in messages)
    reply = "You said: " + (_text_of(user_messages[-1]) if user_messages else "")
    usage = {
        "prompt_tokens": _rough_tokens(prompt_text),
        "completion_tokens": _rough_tokens(reply),
    }
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    model = body.get("model", "mock")
    created = int(time.time())

    await asyncio.sleep(latency_seconds())

    # Test hook: model "mock-error-500" simulates a provider failure.
    if model == "mock-error-500":
        return JSONResponse({"error": {"message": "simulated provider error"}}, status_code=500)

    if not body.get("stream"):
        return JSONResponse({
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                         "finish_reason": "stop"}],
            "usage": usage,
        })

    include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
    size = chunk_chars()

    async def events():
        base = {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model}
        yield "data: " + json.dumps({**base, "choices": [
            {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}) + "\n\n"
        for i in range(0, len(reply), size):
            yield "data: " + json.dumps({**base, "choices": [
                {"index": 0, "delta": {"content": reply[i:i + size]}, "finish_reason": None}]}) + "\n\n"
        yield "data: " + json.dumps({**base, "choices": [
            {"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
        if include_usage:
            yield "data: " + json.dumps({**base, "choices": [], "usage": usage}) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/_received")
async def received():
    return list(RECEIVED)


@app.get("/health")
async def health():
    return {"status": "ok"}

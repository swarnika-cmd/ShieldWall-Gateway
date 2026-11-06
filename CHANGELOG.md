# Changelog

## v2.0.0 (Nov 2026): security & correctness

Breaking: clients must now send `Authorization: Bearer sw_...` (project key).
`X-Project-ID` is ignored. Admin endpoints need `ADMIN_TOKEN`.

### Security

| Bug in v1 | Fix in v2 | Test |
|---|---|---|
| **Open proxy.** The project was whatever `X-Project-ID` the client sent, and if the client sent no `Authorization`, the gateway attached the server's own Groq/OpenAI key. Anyone who could reach the gateway could spend the owner's provider account. | `projects` table with per-project keys (only `sha256(key)` stored); keys minted by `scripts/create_project.py`. Unauthenticated requests get `401` before anything else runs. The gateway's provider key is used only for authenticated projects and the client's key is never forwarded. | `test_auth.py` |
| **Raw PII exposed.** `GET /api/security/logs` was unauthenticated and returned the full placeholder-to-value mapping read from Redis; the mapping also sat in Redis for 5 min. `verify_gateway.py` asserted this behaviour. | The mapping is never written anywhere: it lives in the request's memory only, which is all unmasking needs. Logs and the API keep entity types and counts (`pii_entities`). All `/api/*` routes require `ADMIN_TOKEN`, compared with `hmac.compare_digest`. | `test_chat_e2e.py` scans the Postgres row and every Redis key for raw values |
| Relevance-eval payload carried the **unmasked** response text and the raw RAG query through the Redis broker. | Eval is off by default; when on, only masked query and context are queued, and the response text is not sent at all. | `test_chat_e2e.py` |

Design note on the PII mapping: an earlier plan was to keep it in Redis with a
600 s TTL (optionally Fernet-encrypted). Once the dashboard stopped showing raw
values nothing read it back, so storing it would only add a place for PII to leak.

### Correctness

| Bug in v1 | Fix in v2 | Test |
|---|---|---|
| **Placeholder collision.** `mask_pii` reset its counter for every message but shared one mapping dict, so `a@x.com` in message 1 and `b@y.com` in message 2 both became `[REDACTED_EMAIL_1]`; the second overwrote the first and unmasking returned the wrong email. | One `PiiMasker` per request, one counter across all messages; same value reuses its placeholder. Unmasking is a single regex pass. | `test_placeholders_are_unique_across_messages` |
| **Budget race.** Budget check and cost recording were separate Redis calls, the cost was recorded only after the response, and the limit was a hardcoded $5 per 10 min for everyone. 50 concurrent requests all passed the check. | Redis Lua script atomically checks `spent + reserved + estimate <= budget` and reserves the estimate (output capped with `max_tokens`). A second script reconciles with the provider's real usage. Holds expire if a process dies. Budget is per project per calendar month, from Postgres. Money is integer micro-USD. | `test_concurrent_requests_never_overspend` (50 requests, exactly 7 fit); `test_lua_reserve_vs_naive_check_then_add` shows the v1 approach overspending |
| **Unsafe DB access.** psycopg2 `SimpleConnectionPool` (not thread-safe) was used from `asyncio.to_thread` worker threads; the schema was created only when a Celery worker started. | psycopg 3 `AsyncConnectionPool` opened in the FastAPI lifespan; `schema.sql` (idempotent, advisory-locked) runs at API startup. The worker uses one sync connection per process/thread. | `test_schema_is_idempotent`; every integration test runs on a fresh startup |
| **Card regex** matched any 13-16 digit run (order ids, timestamps). | Luhn check plus card-network first digit. Added Aadhaar (Verhoeff checksum), PAN, Indian mobile. | `test_pii.py` positive and hard-negative cases |
| **Stream text dropped.** Text held back while waiting for a placeholder to complete was flushed only on `[DONE]`; if upstream closed early it was lost. Non-200 upstream errors were streamed with status 200. | `StreamUnmasker.flush()` runs whenever the stream ends; held text is also released before a `finish_reason` chunk. Upstream status is checked before streaming starts. Clean-up is shielded from client-disconnect cancellation so the budget is always reconciled. | Hypothesis property tests over random chunk boundaries; `test_relay_flushes_when_upstream_ends_without_done` |
| **Mislabelled metric.** `avg_overhead_ms` was the average upstream latency. | Gateway records `gateway_overhead_ms` (handler time minus upstream wait, minus client wait for streams) and `upstream_ms` separately; summary reports p50/p99 of each. | `test_summary_reports_overhead_and_upstream_separately` |
| `blocked_injections` counted `MALICIOUS_INJECTION`, which nothing ever produced. | Renamed to `blocked_requests` (budget blocks). No injection detection is claimed. | |
| A failed upstream call raised `HTTPException`, which silently discarded the background task that should release the budget hold. | Return the error response instead so background work still runs. | `test_upstream_errors.py` |

### Performance

| Issue | Change | Evidence |
|---|---|---|
| `/api/analytics/summary` scanned the whole table every 5 s; other queries read heap pages for every row in the window; an index on `(tenant_id, timestamp)` was never used. | All dashboard queries take a time window. New covering index `(timestamp) INCLUDE (...)` and partial index for violation rows; unused v1 indexes dropped. | `docs/db-indexing.md`: 24h queries go from bitmap heap scans (~2,900 pages) to index-only scans (~120 pages); summary from 14 ms full scan to 2 ms. Gains on security logs are negligible and said so. |
| Tokenizer vocabulary loaded on the first request (~150 ms). | Loaded at startup. | |

### "Faithfulness" score

v1 stored the output of `cross-encoder/ms-marco-MiniLM-L-6-v2` on (context chunk, response) pairs as
"faithfulness". That model is trained to rank passages by relevance to a search
query; it does not check whether an answer is supported by its context, so the
name overstated what was measured. v2 keeps only the use the model was trained
for, query-to-context relevance, stored as `relevance_score`, and makes it
optional (`ENABLE_RELEVANCE_EVAL=false` by default). `torch` and
`sentence-transformers` moved to `requirements-eval.txt`; the default image is
now 355 MB (arm64, as reported by `docker images`). The v1 image size was not measured. Existing `context_relevance` values are
migrated to `relevance_score`; the `faithfulness` column is dropped.

### Infrastructure

- `docker-compose.yml` runs api, worker, postgres, redis and a mock provider as
  separate services. The single-container Hugging Face Spaces entrypoint (Celery
  and uvicorn in one container) was removed.
- `mock_upstream/`: OpenAI-compatible fake provider with fixed latency.
- `verify_gateway.py` replaced by a pytest suite (`tests/`), run in Docker
  (`docker-compose.test.yml`) and in GitHub Actions with service containers.
- `bench/`: k6 benchmark of gateway overhead against the mock provider.
- Container runs as a non-root user; dependencies pinned.
- README rewritten: removed claims that were never measured ("under 15 ms",
  "zero performance degradation", "enterprise").

# ShieldWall Gateway

A self-hosted, OpenAI-compatible proxy that sits between your applications and
an LLM provider (OpenAI, Groq, or anything that speaks `/v1/chat/completions`).

What it does on every request:

1. **Authenticates** the calling project with its own API key (`sw_...`).
   The provider key never leaves the gateway.
2. **Masks PII** in the prompt (emails, card numbers, Aadhaar, PAN, Indian
   mobile numbers, US SSNs, some API keys) before it reaches the provider,
   and puts the original values back into the answer, including streamed answers.
3. **Enforces a monthly budget per project** by atomically reserving the
   worst-case cost in Redis before calling the provider, then reconciling
   with the real cost afterwards.
4. **Logs** cost, latency and which kinds of PII were masked (counts only) to
   Postgres through a Celery worker, for the admin dashboard.

It is a student project built to learn backend engineering. It has a test
suite and a reproducible benchmark, but it has not been security-audited or
run in production.

## Architecture

```mermaid
flowchart LR
    C[Client app] -->|Bearer sw_...| A[Auth<br/>sha256 key lookup<br/>60 s cache]
    A --> M[PII mask<br/>regex + checksums]
    M --> B[Budget reserve<br/>Redis Lua, atomic]
    B -->|masked prompt<br/>+ gateway's provider key| U[Upstream LLM]
    U --> S[Unmask<br/>stream-safe buffer]
    S --> C
    S -.after response.-> R[Reconcile real cost<br/>Redis Lua]
    S -.after response.-> Q[(Redis queue)]
    Q --> W[Celery worker] --> P[(Postgres<br/>request_logs)]
    D[Admin dashboard] -->|Bearer ADMIN_TOKEN| X["Admin API /api/*"] --> P
```

- **Hot path** (adds latency to every call): auth, masking, one Redis Lua
  call, the upstream call, unmasking.
- **Async path** (after the response is sent): budget reconciliation, then
  the log row goes through Celery to Postgres. Postgres is only on the hot
  path for an API-key lookup when the key is not in the in-process cache.

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app, request lifecycle, upstream proxying (normal and streaming) |
| `auth.py` | Project API keys, admin token check |
| `pii.py` | PII rules, Luhn and Verhoeff checksums, per-request masker |
| `streaming.py` | Unmasking placeholders that are split across SSE chunks |
| `budget.py` | Redis Lua scripts for reserve and reconcile |
| `pricing.py` | Token estimates and cost in integer micro-USD |
| `db.py` | psycopg 3 async pool (API) and sync connections (worker, scripts) |
| `admin_api.py` | `/api/*` dashboard endpoints |
| `tasks.py` | Celery tasks: write logs, optional relevance scoring |
| `schema.sql` | Idempotent schema, applied by the API at startup |
| `mock_upstream/` | Fake OpenAI-compatible provider for tests, demo and benchmarks |

## Threat model: what this protects and what it does not

Protects against:

- **Anyone using your provider key through the gateway.** Requests without a
  valid project key get `401` and never reach the provider.
- **A project overspending its monthly budget**, including under heavy
  concurrency (tested with 50 parallel requests; see `tests/integration/test_budget.py`).
- **Raw PII in logs or the dashboard.** The token-to-value mapping lives only in
  the gateway process memory for the duration of one request. Postgres and
  Redis store entity types and counts only (`{"EMAIL": 2}`).
- **Common PII formats leaving your network**, within the limits below.

Does NOT protect against:

- **PII the regexes do not recognise.** Names, postal addresses, dates of
  birth, free-text descriptions, unusual number formats, PII inside images or
  files are all sent to the provider unmasked. Regex masking has false negatives; treat it as a safety net, not a guarantee.
- **False positives.** A 16-digit number that happens to pass Luhn and start
  with 2-6 or 8 is masked as a card number (roughly 1 in 10 random 16-digit
  numbers with such a prefix pass Luhn).
- **The provider inferring the masked value** from context, or the model
  ignoring placeholders.
- **A compromised gateway host.** Whoever controls the process sees raw prompts.
- **Small budget overshoot from tokenizer mismatch.** The reservation uses a
  tiktoken estimate; the reconciliation uses the provider's reported usage. For
  non-OpenAI models these can differ slightly.
- **Key theft.** Keys are bearer tokens: anyone holding one can spend that
  project's budget. Revoking a key (delete the row) takes up to 60 s because of
  the auth cache.
- **Request floods.** There is no per-second rate limit, only a monthly budget.
  Invalid keys are not cached, so a flood of bad keys hits Postgres (one indexed lookup each).

### Failure modes

| Failure | Behaviour |
|---|---|
| Redis down | `503` for chat requests by default (`BUDGET_FAIL_MODE=closed`): without Redis the budget cannot be enforced. Set `open` to let traffic through unmetered. Log rows are lost while the Celery broker is down. |
| Postgres down | Cached keys keep working (up to 60 s); unknown keys get `503`. Admin API returns `500`. Celery retries nothing; log rows are dropped. |
| Gateway crashes mid-request | The budget hold expires after `RESERVATION_TTL_SECONDS` (600 s) and is swept by the next reservation. |
| Provider down / 5xx | Client gets `502` (or the provider's status); the hold is released and nothing is charged. |
| Stream cut off before `[DONE]` | Any text held back for unmasking is flushed. If the connection broke (rather than closing cleanly), an error event follows. |

## Quick start (Docker Compose)

Requirements: Docker with Compose v2.

```bash
cp .env.example .env              # set ADMIN_TOKEN to a long random string
docker compose up --build -d      # api, worker, postgres, redis, mock-upstream
```

The gateway listens on `http://localhost:8000` (change with `SHIELDWALL_API_PORT`).
By default it forwards to the bundled mock provider, so no LLM key is needed.
To use a real provider, set `UPSTREAM_URL` and `UPSTREAM_API_KEY` in `.env`.

### Create a project key

```bash
docker compose exec api python scripts/create_project.py --name my-app --budget-usd 25
```

The key is printed once. Only its SHA-256 hash is stored.

### Call it

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sw_..." \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "I am riya@example.com"}]}'
```

The mock echoes what it received. The provider sees `[REDACTED_EMAIL_1]`;
you get your email back. Any OpenAI SDK works by setting `base_url` to
`http://localhost:8000/v1` and `api_key` to the `sw_` key.

### Dashboard

Open `http://localhost:8000/` and paste the `ADMIN_TOKEN`. The token is kept
in the browser tab's `sessionStorage`. The built files in `dashboard/dist`
are committed; rebuild with `cd dashboard && npm ci && npm run build`.

## API reference

### `POST /v1/chat/completions`

OpenAI-compatible. Requires `Authorization: Bearer sw_...`.

- Extra OpenAI fields (`temperature`, `tools`, ...) are forwarded unchanged.
- If neither `max_tokens` nor `max_completion_tokens` is set, the gateway sets
  `max_tokens=DEFAULT_MAX_OUTPUT_TOKENS` (1024) so the cost reservation is an upper bound.
- Optional `user_query` and `rag_context` are stripped before forwarding and
  used only for relevance scoring (if enabled).
- Response header `X-ShieldWall-Request-Id` identifies the log row.

| Status | Meaning |
|---|---|
| 200 | Success (JSON or `text/event-stream`) |
| 401 | Missing or invalid project key |
| 429 | Monthly budget would be exceeded. Header `X-ShieldWall-Reason: budget_exceeded`; body has `budget_usd`, `spent_usd`, `reserved_usd` |
| 502 | Provider unreachable, or provider rejected the gateway's key |
| 503 | Redis (budget store) or Postgres (key store) unavailable |

### Admin API (`/api/*`)

All require `Authorization: Bearer <ADMIN_TOKEN>`. If `ADMIN_TOKEN` is not set
on the server they return `503`. `window` is one of `1h`, `24h` (default), `7d`, `30d`.

| Endpoint | Returns |
|---|---|
| `GET /api/analytics?window=` | `requests`, `total_cost`, `p95_latency_ms`, `avg_relevance_score` |
| `GET /api/analytics/tenants?window=` | spend per project |
| `GET /api/analytics/summary?window=` | `total_spend`, `blocked_requests`, `gateway_overhead_ms_p50/p99`, `upstream_ms_p50` |
| `GET /api/security/logs?window=&limit=` | recent requests with a violation, with `pii_entities` counts (never values) |

`gateway_overhead_ms` is the time spent inside the gateway's handler minus the
time spent waiting for the provider (and, for streams, minus time waiting on
the client). It does not include HTTP parsing in uvicorn; the benchmark
measures that end to end.

`GET /health` (no auth) reports Redis and Postgres status.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/shieldwall` | Postgres |
| `REDIS_URL` | `redis://localhost:6379/0` | Budget store and Celery broker |
| `UPSTREAM_URL` | OpenAI, or Groq if `GROQ_API_KEY` is set | Provider endpoint |
| `UPSTREAM_API_KEY` | falls back to `GROQ_API_KEY`, then `OPENAI_API_KEY` | Gateway's provider key |
| `ADMIN_TOKEN` | empty (admin API disabled) | Dashboard / admin API token |
| `BUDGET_FAIL_MODE` | `closed` | `closed` or `open` when Redis is down |
| `DEFAULT_MAX_OUTPUT_TOKENS` | `1024` | Output cap when the client sets none |
| `RESERVATION_TTL_SECONDS` | `600` | When an unreconciled hold is dropped |
| `AUTH_CACHE_TTL_SECONDS` | `60` | In-process key cache lifetime |
| `UPSTREAM_MAX_CONNECTIONS` / `UPSTREAM_MAX_KEEPALIVE` | `500` / `100` | Size of the httpx connection pool towards the provider. Every request makes httpcore scan the pooled connections, so the size affects event-loop CPU under load |
| `DB_POOL_MIN` / `DB_POOL_MAX` | `1` / `10` | API's Postgres pool |
| `ENABLE_RELEVANCE_EVAL` | `false` | Score retrieval relevance in the worker (needs `requirements-eval.txt`, build with `--build-arg INSTALL_EVAL=true`) |

Budgets are in USD because provider prices are in USD. Money is stored in
Redis as integer micro-USD so the Lua scripts add and compare exactly.

## Tests

```bash
docker compose -f docker-compose.test.yml run --rm --build tests
docker compose -f docker-compose.test.yml down -v
```

104 tests (pytest, run via `docker-compose.test.yml`):

- `tests/unit`: PII rules with positive and hard-negative cases, Luhn and
  Verhoeff vectors, stream unmasking (including Hypothesis property tests that
  split text at random chunk boundaries), pricing.
- `tests/integration`: real Postgres and Redis, the gateway in-process, the
  mock provider on a local port. Covers 401s, admin token, 50 concurrent
  requests against a budget that fits exactly 7, a naive check-then-add
  version that overspends (to show why Lua is needed), streaming and
  non-streaming end to end (provider sees only placeholders, client gets
  originals, nothing raw in Postgres or Redis), upstream failures, and
  migration idempotency.

CI (`.github/workflows/ci.yml`) runs the same tests on Python 3.11 with
`postgres:16` and `redis:7` service containers and the same `DATABASE_URL` /
`REDIS_URL` variables.

## Benchmarks

`bench/run.sh` measures the latency the gateway adds, using k6 against the
mock provider (fixed 200 ms latency): scenario A calls the mock directly,
scenario B goes through the gateway, at 50 and 200 requests/s for 30 s each.
Overhead = B minus A at p50/p95/p99. It also prints the gateway's own
`gateway_overhead_ms` from Postgres as a cross-check.

```bash
bench/run.sh            # full run, use an idle machine
bench/run.sh --quick    # 10 req/s for 5 s, smoke test only
```

Results are written to `bench/results/summary.md` and `bench/results/k6-summary.json`.

### Results (Nov 2026)

Apple M4 Pro, Docker Desktop Linux VM. One uvicorn worker (cpuset of 2 vCPUs), Celery,
Postgres, Redis, the mock provider and k6 each pinned to their own vCPUs. Non-streaming
requests whose prompt contains an email and a phone number, so every request is masked and
unmasked. Raw output: `bench/results/sweep-50-200/` and `bench/results/sweep-100-150/`.

| Rate | Gateway overhead p50 / p95 / p99 (k6) | In-app `gateway_overhead_ms` p50 / p99 | Errors |
|---:|---|---|---:|
| 50 req/s (30 s) | 1.27 / 1.84 / 2.79 ms | 0.48 / 1.89 ms | 0% |
| 100 req/s (20 s) | 1.07 / 1.47 / 5.74 ms | 0.44 / 2.55 ms | 0% |
| 150 req/s (20 s) | 1.03 / 2.60 / 9.94 ms | 0.34 / 3.45 ms | 0% |
| 200 req/s (30 s) | saturated: p50 1.9 s, p99 6.3 s | n/a | 3.96% |

What this shows:

- Up to 150 req/s, the gateway adds about 1 ms at p50 and under 10 ms at p99 on top of the
  provider call, and the in-app timer agrees.
- **On that run, a single worker saturated between 150 and 200 req/s.** Past that point requests
  queue inside the one event loop and latency grows without bound. Conditions differed (one 30 s
  run per point, unpinned k6, host load not recorded for that run); the cause was not isolated. The repeated idle-machine sweep in "Results: before and
  after the `sniffio` fix, and 1 vs 2 workers" below supersedes it for single-worker capacity.
  See "Where the time goes" below for the profile of that saturated state.
- These are local numbers on one machine, not production capacity.

### Results: before and after the `sniffio` fix, and 1 vs 2 workers

`bench/sweep_v3.sh` (script and summariser: `bench/sweep_v3.sh`, `bench/sweep_summary.py`); raw runs,
every k6 summary and a `meta.txt` per run: `bench/results/sweep-v3/`; the full per-run table (nothing
averaged) is `bench/results/sweep-v3/summary.md`.

Method and hardware. All runs 2026-11-13, 01:13 to 03:12 UTC. Apple M4 Pro host, Docker Desktop
Linux VM with 12 vCPUs / 7.7 GiB. API container on cpuset 0-1 (2 vCPUs). Mock upstream with a fixed
200 ms latency. k6 0.54.0 (`grafana/k6:0.54.0`), constant-arrival-rate, 60 s per run, same request
as above. 3 repetitions per configuration, interleaved, with the variant order rotated per repetition,
30 s cool-down between runs and a fresh stack for each run. Celery worker and mock upstream always
run the fixed image. A run is healthy when errors < 1%, dropped iterations = 0 and p95 < 400 ms
(2 x the mock latency). Healthy and unhealthy runs are never averaged together: the medians
below are over healthy runs only, unhealthy runs are listed separately. Variants: before = image
without `sniffio`, pool 500/100; after = `sniffio==1.3.1` installed, pool 500/100; alt = `sniffio`
installed, pool 100/100 (only run at 200 and 250 req/s).

Part A, one worker, before vs after:

| Rate (req/s) | Variant | Healthy runs | Healthy runs: median p50 / p95 / p99 (ms) | Unhealthy runs: median p50 / p95 / p99 (ms) | Unhealthy runs: median errors, median dropped |
|---:|---|---|---|---|---|
| 150 | before | 3 of 3 | 201.7 / 203.0 / 204.0 | none | - |
| 150 | after | 3 of 3 | 201.6 / 202.8 / 203.7 | none | - |
| 200 | before | 3 of 3 | 201.5 / 202.9 / 204.1 | none | - |
| 200 | after | 3 of 3 | 201.4 / 202.6 / 203.5 | none | - |
| 200 | alt | 3 of 3 | 201.4 / 202.6 / 203.5 | none | - |
| 250 | before | 3 of 3 | 201.3 / 202.6 / 205.2 | none | - |
| 250 | after | 3 of 3 | 201.3 / 202.5 / 203.9 | none | - |
| 250 | alt | 3 of 3 | 201.3 / 202.6 / 203.8 | none | - |
| 300 | before | 1 of 3 | 201.6 / 203.3 / 207.8 | 510.3 / 4226.9 / 7006.2 | 2.92%, 1075 |
| 300 | after | 2 of 3 | 201.4 / 202.9 / 206.1 | 201.9 / 4809.7 / 6327.7 | 2.52%, 1191 |

Reading it:

- At 150, 200 and 250 req/s both builds were healthy in 3 of 3 runs, with near-identical medians.
- At 300 req/s, before was healthy in 1 of 3 runs and after in 2 of 3. That is not a claimable
  difference (the rule used here is that only 0 of 3 against 3 of 3 counts), so the runs show no
  throughput difference between the builds on one worker.
- The fix shows up in the CPU profile (next table), not as a measurable single-worker throughput gain.
  The data do not support saying it raised capacity.
- On this idle run the original build (before) sustained 250 req/s in 3 of 3 runs. The earlier
  committed sweep (`bench/results/sweep-50-200/`) saturated at 200 req/s. Conditions differed (one 30 s run per point, unpinned k6, host load not recorded for
  that run); the cause was not isolated. The idle-machine sweep supersedes it for single-worker capacity.

Part B, scaling, variant after, pool 500/100. The 1-worker and 2-worker runs at each rate were run
back to back within each repetition. The 2-worker stack uses the same cpuset 0-1 as the 1-worker runs.

| Rate (req/s) | 1 worker: healthy runs; healthy median p50 / p95 / p99 (ms) | 2 workers: healthy runs; healthy median p50 / p95 / p99 (ms) |
|---:|---|---|
| 150 | 3 of 3; 201.6 / 202.9 / 203.9 | 3 of 3; 201.7 / 202.9 / 203.7 |
| 200 | 3 of 3; 201.4 / 202.6 / 203.7 | 3 of 3; 201.5 / 202.7 / 203.6 |
| 300 | 2 of 3; 201.4 / 202.9 / 206.0 | 3 of 3; 201.4 / 202.7 / 203.8 |
| 400 | 0 of 3; none | 3 of 3; 201.5 / 203.0 / 206.3 |

- 1 worker: healthy in 3 of 3 runs at 150 and 200 req/s, 2 of 3 at 300 and 0 of 3 at 400. At 400 req/s
  the three 1-worker runs had 12.98% to 15.84% errors, median p50 950.0 ms, median p95 9041.5 ms.
- 2 workers: healthy in 3 of 3 runs at every rate tested (150, 200, 300, 400 req/s).
- At 400 req/s with 2 workers: healthy median p50 / p95 / p99 201.5 / 203.0 / 206.3 ms against the
  200 ms mock; in-app `gateway_overhead_ms` p99 1.324 to 1.631 ms across the three runs; API
  container CPU mid-run 75.88% to 83.34% (the figure `docker stats` reports for the container).
- Nothing was tested above 400 req/s, so no maximum is claimed, and this is not a linear-scaling
  claim. k6 (4 vCPUs) and the mock upstream (2 vCPUs) share the VM and may limit the highest rates.

Profile at 50 req/s, one worker, py-spy `--gil`, 60 s, 100 Hz, event-loop thread only. Flame graphs:
[`docs/profiling/flame-1worker-50rps-before.svg`](docs/profiling/flame-1worker-50rps-before.svg),
[`docs/profiling/flame-1worker-50rps-after.svg`](docs/profiling/flame-1worker-50rps-after.svg); tables:
[`gil-50rps-before.md`](docs/profiling/analysis/gil-50rps-before.md),
[`gil-50rps-after.md`](docs/profiling/analysis/gil-50rps-after.md).

| Bucket | Before (1104 loop samples) | After (1212 loop samples) |
|---|---:|---:|
| httpcore per-call import probe (`current_async_library` -> importlib) | 6.2% (69) | 0.9% (11) |
| httpcore connection-pool scan | 3.2% (35) | 4.0% (49) |
| httpx/httpcore other | 28.7% (317) | 26.4% (320) |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 37.2% (411) | 42.7% (518) |
| Redis round trips (budget) | 15.1% (167) | 14.3% (173) |
| everything else (JSON 3.4% / 2.9%, event loop idle 2.1% / 3.1%, regex PII 1.8% / 2.1%, tiktoken 1.1% / 0.7%, DB 0.6% / 1.4%, to_thread dispatch 0.5% / 1.4%) | 9.5% (105) | 11.6% (141) |

(Each sample goes to the first matching bucket; columns add to 100%.) The probe fell from 6.2% to
0.9%. Each variant is one 60 s window; the noise of the small buckets was not quantified, so
the other differences in the table (for example the framework share) should not be interpreted.
k6 outcome with py-spy attached: before 203.6 / 207.8 / 210.0 ms p50 / p95 / p99, 0.00% errors, 0
dropped; after 203.4 / 207.6 / 209.6 ms, 0.00% errors, 0 dropped.

### Where the time goes at saturation

Profiled with `py-spy` against one uvicorn worker at 200 req/s (`bench/profile.sh`, method,
hardware, date and every run in [`docs/profiling/README.md`](docs/profiling/README.md); flame graph:
[`docs/profiling/flame-1worker-200rps.svg`](docs/profiling/flame-1worker-200rps.svg)).
Share of event-loop samples by bucket (each sample counted once):

| Bucket | Healthy run, 50 req/s (GIL held) | Saturated, 200 req/s (GIL held) | Saturated, 200 req/s (wall clock) |
|---|---:|---:|---:|
| httpcore connection-pool scan | 4.7% | 46.2% | 53.5% |
| httpcore `import sniffio` probe (module not installed) | 6.5% | 7.5% | 15.1% |
| httpx/httpcore other | 29.6% | 21.2% | 13.1% |
| framework / residual (uvicorn, starlette, fastapi, anyio) | 38.9% | 12.7% | 8.9% |
| Redis round trips (budget) | 13.0% | 6.9% | 6.1% |
| event loop idle (stack ends at the asyncio runner) | 1.8% | 1.6% | 1.0% |
| regex PII scans | 1.5% | 1.5% | 0.6% |
| JSON / pydantic | 1.8% | 1.2% | 0.5% |
| tiktoken | 0.5% | 0.4% | 0.8% |
| asyncio.to_thread dispatch, DB, logging | 1.8% | 0.9% | 0.5% |

A sample that matches both the import probe and the pool scan (the probe runs inside the scan) is
counted as the import probe.

- The earlier guess (tokenizer, regex, JSON, Redis and Celery) did not hold for tokenizer, regex and
  JSON, which are each under 2% of event-loop samples in every run (Redis is 4.6% to 13.0% of loop
  samples; Celery publishing holds the GIL for 6.7% to 9.2% of GIL-held samples). At saturation the
  loop spends most of its samples in httpcore's per-request scan of the pooled connections (a poll
  per idle connection) and in an `import sniffio` that fails and searches the import path on every
  call.
- Celery publishing is a synchronous call, but it runs in a worker thread (`asyncio.to_thread`),
  not on the loop.
- Caveats. Attaching py-spy changed the outcome: every profiled run at 75 req/s or more went into
  the saturated state, including 10 Hz and non-blocking sampling, while unprofiled controls at
  100 req/s stayed clean. So the saturated profiles show the saturated state, not what tips a
  healthy run over. The healthy column is one 60 s window with 877 loop samples. The machine was
  shared and busy during these runs.
- Changes made in response: `sniffio` is now installed (with `httpcore` pinned to 1.0.9), so the
  import becomes a cached lookup instead of a failing path search on every call; and the size of
  the upstream connection pool is configurable (`UPSTREAM_MAX_CONNECTIONS` /
  `UPSTREAM_MAX_KEEPALIVE`, defaults unchanged at 500 / 100). `bench/sweep_v3.sh` measures before
  and after: repeated, interleaved runs with the variant order rotated per repetition, and for the
  multi-worker scaling the 1-worker and N-worker runs at each rate are run back to back within each
  repetition, so each pair sees similar machine conditions.

## Multi-worker budget correctness

The budget check-and-hold is one Lua script executed atomically by Redis, so adding uvicorn
workers (`UVICORN_WORKERS` in the bench stack) does not let requests overspend a project's budget.
`scripts/budget_race_check.py` checks this over HTTP, which the in-process integration test cannot.
It creates a project whose budget is `7 * estimate + estimate // 2`, where `estimate` is the
worst-case reservation of one request (for `gpt-4o`, 17 input tokens and `max_tokens` 100:
`17 * 5 + 100 * 15 = 1585` micro-USD, so a budget of 11887 micro-USD). A request is granted only if
`spent + reserved + estimate <= budget`; with nothing finished yet, the 8th request would need
`8 * 1585 = 12680 > 11887`, so exactly 7 of 50 concurrent requests get a 200 and 43 get a 429. The
script asserts that count exactly, plus no leftover holds in Redis and spend within the budget.
The mock provider is set to 800 ms so all 50 reservations happen before any is released. Result,
3 checks on 2 workers (API cpuset 0-1), each attempt 1 of 3: `expected 200s = 7, 429s = 43`, observed
`200=7 429=43`, `holds=0`, `worker processes found: 2; used CPU during the burst: 2`, 3 of 3 PASS
(the script requires at least 2 busy workers and the 429 reason header). Output with its provenance
header (command, host, date 2026-11-13 03:04 UTC): `bench/results/sweep-v3/budget-race.txt`
(Part R of `bench/sweep_v3.sh`, `SWEEP_RACE="2:0-1"`).

An earlier run with an earlier revision of the script, 3 runs each on 1, 2 and 4 workers, also gave
7 x 200 and 43 x 429 every time with holds 0 (9 of 9 PASS): `bench/results/sweep-v3-race/budget-race.txt`,
produced on 2026-11-12 (UTC 23:47) on the same host and Docker VM, API container cpuset 0-1 (0-3 for
the 4-worker stack), by `SWEEP_COOLDOWN=3 SWEEP_OUT=results/sweep-v3-race SWEEP_RACE="1:0-1 2:0-1 4:0-3" bench/sweep_v3.sh R`.
That revision printed which worker processes used CPU during the burst but did not enforce it (every
worker in the 2-worker runs and in two of the three 4-worker runs; 2 of 4 in the other) and did not
check the 429 reason header. The current script enforces both. The 4-worker case has not been re-run
with the current script.

## PII detection: precision and recall

`scripts/make_pii_dataset.py` builds a labelled set (seed 20261113, 1,000 sentences, 742 labelled
spans: emails, Indian mobiles, PAN, Aadhaar with valid Verhoeff checksums, Luhn-valid cards, plus
hard negatives such as order ids, timestamps, 16-digit non-Luhn and 12-digit non-Verhoeff numbers,
invoice numbers, non-Indian phone numbers and malformed PAN-like strings).
`scripts/eval_pii.py` runs `pii.py` over it; a prediction matches a labelled span when the type is
the same and the spans overlap. Details: `bench/results/pii-eval.md`.

| Type | Labelled | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| AADHAAR | 119 | 119 | 1 | 0 | 0.992 | 1.000 | 0.996 |
| CREDIT_CARD | 142 | 142 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| EMAIL | 176 | 176 | 15 | 0 | 0.921 | 1.000 | 0.959 |
| IN_MOBILE | 185 | 184 | 0 | 1 | 1.000 | 0.995 | 0.997 |
| PAN | 120 | 120 | 0 | 0 | 1.000 | 1.000 | 1.000 |

These measure this dataset, whose negatives I chose; they are not production rates. The numeric
negatives (order ids, references, 16-digit numbers) were constructed to fail their checksums, so
precision is measured against checksum-invalid lookalikes. By arithmetic, about 1 in 10 random
12-digit references (first digit 2-9) pass Verhoeff and about 1 in 10 random 13 to 19 digit numbers
starting with 2-6 or 8 pass Luhn by chance, and those would be masked; this is a probability, not a
measurement. Recall covers only the formats the generator emits. Known gaps, each pinned by a test in
`tests/unit/test_pii_known_gaps.py`: mobiles written like `98-7654-3210` or `9876-543210`, lowercase
PANs, and Aadhaar numbers with mixed separators (`2341 2341-2346`) are not detected. Two known
limitations of what is detected:

- A mobile written as `+91XXXXXXXXXX` with no separator is a 12-digit string; about 1 in 10 pass the
  Verhoeff check by chance and are masked as AADHAAR instead of IN_MOBILE (still masked, wrong label).
- File names such as `logo@2x.png` and `git@github.com` (from a git remote) match the email rule and
  are masked as EMAIL (15 false positives, all in the 20-row email-lookalike category).

## Database

See [`docs/db-indexing.md`](docs/db-indexing.md) for the dashboard query
plans before and after v2, measured with `EXPLAIN (ANALYZE, BUFFERS)` on 200k rows.

## Changes from v1

See [`CHANGELOG.md`](CHANGELOG.md).

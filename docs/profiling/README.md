# Profiling the gateway (one uvicorn worker)

Question: why does one worker saturate between 150 and 200 req/s (see `bench/results/sweep-*/summary.md`)? Note: the idle-machine sweep (`bench/results/sweep-v3/`) supersedes the 150-to-200 req/s premise; this analysis covers the earlier saturated state.

- Date: 2026-11-13 IST (runs between 2026-11-12 19:12 and 19:57 UTC).
- Hardware: Apple M4 Pro host, Docker Desktop Linux VM with 12 vCPUs / 7.7 GiB.
- API container: one uvicorn worker (`--workers 1`), `cpuset 0-1` (2 vCPUs), `os.cpu_count()` inside it still reports 12.
- Worker (Celery, 2 vCPUs), Postgres, Redis, mock upstream (200 ms) and k6 are pinned to their own vCPUs, as in `bench/docker-compose.bench.yml`.
- Versions in the image: Python 3.11.18, uvicorn 0.54.0, uvloop 0.23.0, httpx 0.28.1, httpcore 1.0.9, anyio 4.16.0, redis-py 8.1.0, celery 5.7.0, kombu 5.7.0, tiktoken 0.14.0, py-spy 0.4.1.
- The machine was shared with other jobs while this ran. Load average on the host was 8 to 25 on 12 cores during the runs. Treat absolute capacity numbers as noisy; proportions inside one profile are the useful output.
- Payload: the existing `bench/k6/gateway_overhead.js` request (one email and one phone number in the prompt, non-streaming, `gpt-4o-mini`, `max_tokens` 64).

## How it was run

Everything is Docker. `bench/profile.sh` brings up the bench stack under compose project `sw-prof`, runs k6 against the gateway only (`TARGETS=gateway`, constant arrival rate, 150 s), waits for the first logged request, sleeps 12 s, then records two 60 s py-spy windows on the uvicorn worker (pid 1): a flame graph and raw collapsed stacks. It tears the stack down on exit.

```bash
# one-off: tiktoken cache (the image build cannot download the vocab behind the TLS-inspecting proxy;
# the build prints a warning and /opt/tiktoken stays empty, which would make pricing.py use its byte-count fallback)
# CA_PEM: the proxy CA certificate, only needed if the download fails certificate verification
mkdir -p "$TIKTOKEN_CACHE_HOST"
docker run --rm -u root -v "$TIKTOKEN_CACHE_HOST":/opt/tiktoken \
  -v "$CA_PEM":/zs.pem:ro shieldwall-gateway:bench sh -c \
  'cat /etc/ssl/certs/ca-certificates.crt /zs.pem > /tmp/ca.pem; REQUESTS_CA_BUNDLE=/tmp/ca.pem python -c \
   "import tiktoken; tiktoken.get_encoding(\"cl100k_base\"); tiktoken.get_encoding(\"o200k_base\")"'

export TIKTOKEN_CACHE_HOST=/abs/path/to/tiktoken-cache
bench/profile.sh idle                      # 200 req/s, py-spy --idle (wall-clock view)   -> flame-1worker-200rps.svg
bench/profile.sh noidle                    # 200 req/s, idle samples dropped
bench/profile.sh gil                       # 200 req/s, py-spy --gil (only the thread holding the GIL)
PROFILE_RATE=150 bench/profile.sh gil      # and idle
PROFILE_RATE=75  bench/profile.sh gil
PROFILE_RATE=50  bench/profile.sh gil      # healthy run, see below
PROFILE_RATE=100 PROFILE_SPY_ARGS=--nonblocking PROFILE_TAG=nb bench/profile.sh idle
PROFILE_RATE=100 PROFILE_HZ=10 bench/profile.sh gil
PROFILE_RATE=100 PROFILE_DURATION=150s PROFILE_TAG=150s bench/profile.sh none   # controls: same load, no py-spy
PROFILE_RATE=100 PROFILE_DURATION=60s bench/profile.sh none
PROFILE_RATE=150 PROFILE_DURATION=60s bench/profile.sh none
```

The py-spy command inside the container (from `bench/profile.sh`), for the main flame graph:

```bash
py-spy record --pid 1 --rate 100 --subprocesses --idle --threads --format flamegraph -o /out/idle-200rps/flame.svg --duration 60
py-spy record --pid 1 --rate 100 --subprocesses --idle --threads --format raw        -o /out/idle-200rps/stacks.txt --duration 60
```

`py-spy` is installed only in a derived image (`bench/Dockerfile.profile`), added by `bench/docker-compose.profile.yml` together with `cap_add: [SYS_PTRACE]`. The production Dockerfile is untouched. The tokenizer cache is mounted read-only by `bench/docker-compose.tokenizer-cache.yml`. (The README of the repo does not currently describe a tokenizer cache override; this file is the one added here.)

Analysis: `bench/analyze_stacks.py <stacks.txt[.gz]>` writes the tables in `analysis/<run>.md`. Run it in Docker (`python:3.11-slim`, no dependencies):

```bash
docker run --rm -v "$PWD":/app -w /app python:3.11-slim python -I bench/analyze_stacks.py docs/profiling/runs/gil-50rps/stacks.txt.gz --title gil-50rps
```

## Files

| Path | What |
|---|---|
| `flame-1worker-200rps.svg` | Flame graph, 200 req/s, `--idle` (wall-clock), 60 s, 100 Hz |
| `flame-1worker-50rps-before.svg` | Flame graph, 50 req/s, `--gil`, 60 s, 100 Hz, image without `sniffio` (sweep run `P-before-1w-r50`) |
| `flame-1worker-50rps-after.svg` | Same, with `sniffio==1.3.1` installed (sweep run `P-after-1w-r50`) |
| `stacks-1worker-50rps-before.txt.gz`, `stacks-1worker-50rps-after.txt.gz` | Raw collapsed stacks of the two 50 req/s runs |
| `analysis/gil-50rps-before.md`, `analysis/gil-50rps-after.md` | Bucket, inclusive and self tables of the two 50 req/s runs |
| `stacks-1worker-200rps.txt.gz` | Raw collapsed stacks of the second 60 s window of the same run (gzip of plain text, `stack count`; `zcat` it) |
| `analysis/<run>.md` | Bucket, inclusive and self tables per run |
| `runs/<run>/` | `k6-summary.md`, `notes.txt` (date, CPU facts, container CPU), `py-spy-dump.txt`, `flame.svg`, `stacks.txt.gz` |

## Result 1: what the runs look like (read this before the tables)

| Run | k6 gateway p50 / p95 / p99 (ms) | Errors | Gateway requests completed (scheduled) | py-spy |
|---|---|---:|---:|---|
| `none-100rps-150s` (control) | 202.5 / 204.5 / 207.5 | 0.00% | 15001 (15000) | none |
| `none-100rps` (control, 60 s) | 202.5 / 205.3 / 220.4 | 0.00% | 6001 (6000) | none |
| `none-150rps` (control, 60 s) | 2286 / 9026 / 11599 | 2.83% | 7214 (9000) | none |
| `gil-50rps` | 203.0 / 205.6 / 207.7 | 0.00% | 7500 (7500) | blocking, 100 Hz, `--gil` |
| `gil-75rps` | 240 / 8033 / 102205 | 0.69% | 8967 (11250) | blocking, 100 Hz, `--gil` |
| `idle-100rps` | 2252 / 9259 / 14768 | 1.19% | 12396 (15000) | blocking, 100 Hz, `--idle` |
| `idle-100rps-nb` | 2174 / 7783 / 12727 | 1.64% | 13251 (15000) | `--nonblocking`, 100 Hz, `--idle` |
| `gil-100rps-10hz` | 1294 / 7499 / 10679 | 1.54% | 13502 (15000) | blocking, 10 Hz, `--gil` |
| `idle-150rps` / `gil-150rps` | 2881 / 14309 / 25001; 2282 / 7307 / 15259 | 6.75%; 3.53% | 15686; 18691 (22500) | blocking, 100 Hz |
| `idle-200rps` (main flame graph) | 1602 / 12927 / 20128 | 19.58% | 22720 (30000) | blocking, 100 Hz, `--idle` |
| `noidle-200rps` | 8673 / 57445 / 60004 | 14.07% | 7600 (30000) | blocking, 100 Hz |
| `gil-200rps` | 2175 / 16810 / 26429 | 9.92% | 20039 (30000) | blocking, 100 Hz, `--gil` |

What this means:

- At 200 req/s every profile is of a saturated gateway: the event loop thread is almost never idle (`--idle` run: 163 of 5999 loop samples, 2.7%, have no ASGI request frame; 59 samples, 1.0%, are at the bare asyncio runner), the API container is at about 100% of one core (`docker stats`), and k6 runs out of VUs. 150 s at 200 req/s drives it much deeper than the 30 s committed baseline (see the request counts above), so these are collapse profiles, not knee profiles.
- Attaching py-spy changes the outcome. With py-spy attached (blocking or non-blocking, 100 Hz or 10 Hz) every run at 75 req/s and above went into the same collapse, including 100 req/s, where the no-py-spy controls were clean for 60 s and 150 s. In those runs the collapse started within a few seconds of py-spy attaching. I did not isolate whether the trigger is the attach itself or the sampling; I only know that lowering the rate to 10 Hz and using `--nonblocking` did not avoid it.
- The no-py-spy control at 150 req/s (60 s) was already saturated on this run, although the committed baseline says clean at 150. The host was heavily loaded (load average 8 to 25 on 12 cores), so the knee on this machine today is below the committed one. I did not re-measure the baseline.
- Only `gil-50rps` is a healthy-state profile (k6 clean, no errors, 14.9% container CPU). The collapse profiles and the healthy profile agree on what is on the stack but disagree sharply on proportions, which is the main finding.

## Result 2: buckets for the event-loop thread (MainThread)

Each sample goes to the first bucket that matches anywhere in its stack, so columns add to 100%. `gil` runs count only samples where the thread held the GIL. `idle` counts wall-clock samples (the loop thread is idle for only about 1% of samples at 200 req/s, so idle and busy views are close). A sample that matches both the import probe and the pool scan (the probe runs inside the scan) is counted as the import probe. Tables for every run are in `analysis/`.

| Bucket | `gil-50rps` (healthy, GIL held) | `gil-200rps` (saturated, GIL held) | `idle-200rps` (saturated, wall) | `noidle-200rps` (saturated) |
|---|---:|---:|---:|---:|
| httpcore connection-pool scan (`_assign_requests_to_connections`, `is_socket_readable`, `is_idle`, `is_queued`) | 4.7% | 46.2% | 53.5% | 48.7% |
| httpcore per-call `import sniffio` probe (`current_async_library` -> importlib path scan) | 6.5% | 7.5% | 15.1% | 17.5% |
| httpx/httpcore other (request build, send, read) | 29.6% | 21.2% | 13.1% | 16.1% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 38.9% | 12.7% | 8.9% | 8.1% |
| Redis round trips (redis.asyncio, `budget.py`) | 13.0% | 6.9% | 6.1% | 4.6% |
| event loop idle (stack ends at the asyncio runner) | 1.8% | 1.6% | 1.0% | 1.6% |
| regex PII scans (`pii.py`) | 1.5% | 1.5% | 0.6% | 0.4% |
| JSON / pydantic (de)serialisation | 1.8% | 1.2% | 0.5% | 0.7% |
| asyncio.to_thread dispatch/wait | 1.3% | 0.5% | 0.2% | 1.1% |
| tiktoken counting | 0.5% | 0.4% | 0.8% | 0.7% |
| DB (psycopg, `db.py`, `auth.py`) | 0.5% | 0.4% | 0.3% | 0.2% |
| logging | 0% | 0.0% | 0.0% | 0.3% |

Across all nine collapsed-state profiles in `analysis/` the pool-scan share is 46.2% to 65.1% (excluding one run with corrupted stacks, 66.9%); the healthy run's 4.7% is the outlier. The tiktoken, PII, JSON and logging buckets are under 2% each in every run.

## Result 3: worker threads (asyncio.to_thread pool) and Celery

- The default executor is uvloop's (threads are named `uvloop_N`) with `min(32, os.cpu_count() + 4)` = 16 threads here, because `os.cpu_count()` is 12 inside the container even with a 2-vCPU cpuset. 16 threads were seen in the 200 req/s runs; the 50 req/s run only ever used 2.
- The only thing run in that pool is `main.enqueue_log` -> Celery `task.delay()` -> kombu -> synchronous redis-py `LPUSH`. It is 99%+ of the busy pool samples in every run.
- Cost: `idle-200rps`: 2414 of 95984 pool samples (2.5%), i.e. about 0.4 busy threads on average; the rest is idle threads parked in `_worker` waiting for work (97.5%). Under `--gil` the pool holds the GIL for 327 of 4912 samples at 200 req/s (6.7%) and 89 of 966 at 50 req/s (9.2%).
- Self time in the pool is mostly socket send/read in redis-py (`_read_from_socket`, `send_packed_command`), which release the GIL. Python-level work holding the GIL is kombu/celery message building, `uuid4`, redis-py bookkeeping.

## Result 4: top 15 frames, event loop, `idle-200rps` (100 Hz, 6000 samples = 60 s)

Self % (leaf frame, line numbers kept):

| Frame | Self | % |
|---|---:|---:|
| `is_socket_readable (httpcore/_utils.py:37)` | 654 | 10.9% |
| `is_idle (httpcore/_async/http11.py:289)` | 654 | 10.9% |
| `_path_stat (importlib._bootstrap_external:147)` | 451 | 7.5% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 245 | 4.1% |
| `is_idle (httpcore/_async/connection.py:195)` | 206 | 3.4% |
| `_path_importer_cache (importlib._bootstrap_external:1434)` | 156 | 2.6% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 144 | 2.4% |
| `current_task (asyncio/tasks.py:38)` | 128 | 2.1% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 117 | 2.0% |
| `is_idle (httpcore/_async/http11.py:288)` | 103 | 1.7% |
| `is_queued (httpcore/_async/connection_pool.py:40)` | 100 | 1.7% |
| `_ensure_future (asyncio/tasks.py:680)` | 94 | 1.6% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 87 | 1.5% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 69 | 1.2% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 62 | 1.0% |

Inclusive % (ASGI/uvicorn wrapper frames that are on every stack are skipped):

| Frame | Inclusive | % |
|---|---:|---:|
| `chat_completions (main.py)` | 5320 | 88.7% |
| `proxy_non_streaming (main.py)` | 4941 | 82.4% |
| `post (httpx/_client.py)` | 4906 | 81.8% |
| `send (httpx/_client.py)` | 4821 | 80.4% |
| `_send_handling_auth (httpx/_client.py)` | 4282 | 71.4% |
| `handle_async_request (httpx/_transports/default.py)` | 4240 | 70.7% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 4218 | 70.3% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 3636 | 60.6% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1646 | 27.4% |
| `has_expired (httpcore/_async/connection.py)` | 1379 | 23.0% |
| `has_expired (httpcore/_async/http11.py)` | 1361 | 22.7% |

Same table for the healthy run (`gil-50rps`): `chat_completions` 53.4%, `proxy_non_streaming` 43.2%, `post (httpx)` 41.2%, `handle_async_request (httpcore pool)` 23.8%, and `data_received (uvicorn)` 15.4% (see `analysis/gil-50rps.md`). Pool and thread-level tables for the worker threads are in each `analysis/<run>.md`.

## Reading

Evidence-backed:

- The CPU being spent at saturation is inside httpcore's connection pool, on the event loop thread: `handle_async_request` -> `_assign_requests_to_connections` iterates every pooled connection and calls `has_expired` -> `is_socket_readable` (a poll syscall per idle connection) plus `is_idle`/`is_queued` list comprehensions. That is 46.2% to 65.1% of event-loop samples in the nine collapsed-state profiles, against 4.7% in the healthy 50 req/s run. The scan cost per request grows with the number of pooled connections; the pool limit is `UPSTREAM_MAX_CONNECTIONS` (default 500).
- A second, smaller httpcore cost: `current_async_library()` does `import sniffio` on every lock/event creation. `sniffio` is not installed (anyio 4.16 no longer depends on it), so each call fails the import after an importlib path scan (`_path_stat`, `_path_importer_cache`). 5.4% to 17.5% of loop samples across the ten committed profiles.
- The things the README listed as likely costs are not what dominates: tiktoken 0.4% to 0.8%, regex PII 0.4% to 1.5%, JSON 0.5% to 1.8% of event-loop samples in every run, tiktoken confirmed active (frames in `tiktoken/core.py`, not the byte-count fallback).
- Event loop blocking: the loop thread does not wait on any synchronous network client. Redis for the budget is `redis.asyncio`; Celery `.delay()` runs via `asyncio.to_thread` and its sync redis-py call happens in a pool thread. Synchronous CPU work on the loop thread is the pii/tiktoken/json code (under 3% together) and the httpcore pool scan (the big one).
- Celery publishing costs the loop indirectly through the GIL: 6.7% to 9.2% of GIL-held samples are in pool threads. It does not block the loop thread, but it competes with it.

Not established:

- Whether the collapse is a feedback loop (more in-flight requests, larger pool, costlier scan, fewer requests per second, more in-flight requests) is my reading of the 4.7% versus 46.2%-65.1% contrast. I did not count open upstream connections or in-flight requests during a run, and I did not show the pool at its 500-connection cap.
- What tips a healthy run over (py-spy attach, a GC pause, a noisy neighbour) was not isolated. The attach effect was seen at 75 and 100 req/s and not with 10 Hz or `--nonblocking`, so a pure sampling-overhead explanation does not fit; a one-off stall at attach does. Not tested.
- The 150 s, 200 req/s runs are deeper into collapse than the 30 s baseline; proportions at the 30 s knee may differ somewhat.
- The healthy profile is a single 60 s window at 50 req/s with 877 loop samples; with so few samples, small buckets are noisy; the noise was not quantified.
- `idle-100rps-nb` (non-blocking) stacks contain at least one corrupted line (a module docstring fragment was read as a frame); it is kept only for its k6 outcome.
- Effect of any fix (smaller pool, a different HTTP client, installing `sniffio`, more workers) is untested in this phase; it was measured afterwards with `bench/sweep_v3.sh`, see "Changes made afterwards" and the README.

## Multi-worker stack and the 50-request budget check

- Worker count: neither the Dockerfile nor `docker-compose.yml` sets `--workers`, so the API runs one process. `bench/docker-compose.bench.yml` now passes `--workers ${UVICORN_WORKERS:-1}` (default unchanged). Give the container as many vCPUs as workers: `UVICORN_WORKERS=4 BENCH_CPUS_API=0-3 bench/run.sh`. (uvicorn also reads `WEB_CONCURRENCY` when `--workers` is not given.)
- `tests/integration/test_budget.py::test_concurrent_requests_never_overspend` fires 50 concurrent requests, but through `httpx.ASGITransport` into one in-process app, so it cannot see cross-process races. `scripts/budget_race_check.py` runs the same scenario over HTTP against a running stack (7 requests fit the budget, expects 7 x 200, 43 x 429, no leftover holds). Results: `bench/results/sweep-v3/budget-race.txt` (current script, 2 workers, 3 of 3 PASS; provenance header in the file) and, from an earlier revision of the script, `bench/results/sweep-v3-race/budget-race.txt` (3 runs each on 1, 2 and 4 workers, 9 of 9 PASS; see the README for both).

```bash
cd bench
export TIKTOKEN_CACHE_HOST=/abs/path/to/tiktoken-cache
C="docker compose -p sw-multi -f docker-compose.bench.yml -f docker-compose.tokenizer-cache.yml"
MOCK_LATENCY_MS=800 UVICORN_WORKERS=4 BENCH_CPUS_API=0-3 $C up -d --build --wait api worker mock-upstream postgres redis
$C exec -T api python scripts/budget_race_check.py --workers 4
$C down -v
```

## Changes made afterwards

- `requirements.txt`: `httpcore==1.0.9` (the version in the image) and `sniffio==1.3.1`, so the import becomes a cached lookup instead of a failing path search on every call.
- `UPSTREAM_MAX_CONNECTIONS` / `UPSTREAM_MAX_KEEPALIVE` make the httpx pool limits configurable; the defaults stay at 500 / 100.
- `bench/sweep_v3.sh` compares before and after on an idle machine (repeated, interleaved runs; healthy runs reported separately from saturated ones) and takes the 50 req/s py-spy profiles of both, written as `flame-1worker-50rps-before.svg` / `-after.svg` in this directory.

Result (sweep run 2026-11-13 01:13 to 03:12 UTC, `bench/results/sweep-v3/`, tables in the README): at 50 req/s the httpcore per-call import probe fell from 6.2% (69 of 1104 event-loop samples, `analysis/gil-50rps-before.md`) to 0.9% (11 of 1212, `analysis/gil-50rps-after.md`). Both profiles are one 60 s window each; the noise of the small buckets was not quantified. The profile change did not show up as a measurable single-worker throughput difference (see the README).

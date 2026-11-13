"""50 concurrent requests against a RUNNING gateway must grant exactly as many as the budget holds.

HTTP-level twin of tests/integration/test_budget.py::test_concurrent_requests_never_overspend.
That test calls the app in-process, so it only ever exercises one process. Run this script
against a multi-worker stack to check that the Redis reservation is atomic across workers.

What it configures, and why the expected number of 200s is exact
  estimate  = cost_micro_usd(gpt-4o, input_tokens, max_tokens=100) = input_tokens * 5 + 100 * 15 micro-USD
              (gpt-4o is 5.00 / 15.00 USD per 1M tokens = 5 / 15 micro-USD per token; pricing.py).
              input_tokens = estimate_input_tokens(messages) = 2 + 4 per message + tokens(content) + tokens(role).
  budget    = 7 * estimate + estimate // 2 micro-USD, stored in projects.monthly_budget_usd NUMERIC(12,6)
              (exact at micro-USD precision) and read back as int(usd * 1e6) by auth.py.
  reserve() (budget.py RESERVE_LUA) grants a request iff  spent + reserved + estimate <= budget.
  While no request has finished, spent = 0 and reserved = k * estimate after k grants, so the
  (k+1)-th request is granted iff (k + 1) * estimate <= budget = 7 * estimate + estimate // 2,
  i.e. iff k + 1 <= 7. Exactly 7 are granted, the other 43 get 429, however the 50 are spread
  over workers, because the check-and-hold is one Lua script executed atomically by Redis.
  This only holds if all 50 reservations happen before the first reconcile, hence the slow mock
  (MOCK_LATENCY_MS=800 vs. a few ms to send 50 requests). If a request finished early, its freed
  budget could admit an extra one and the count would exceed 7: the script then fails and says so.

It asserts: 200s == expected (computed from the stored budget, and equal to --fits), 429s == the
rest and each carries X-ShieldWall-Reason: budget_exceeded, no holds left in Redis, 0 < spent <= budget.
With --workers N > 1 it also requires that at least 2 worker processes used CPU during the burst (from
/proc); if that is the only thing wrong it retries with a fresh project, up to --retries (2) times, and
prints "PASS (attempts: k)" so the number of attempts is recorded. Any other failure is final.

    # bench stack with N uvicorn workers; slow mock so all reservations land before any is freed
    cd bench
    MOCK_LATENCY_MS=800 UVICORN_WORKERS=4 BENCH_CPUS_API=0-3 \
      docker compose -p sw-multi -f docker-compose.bench.yml up -d --build --wait api worker mock-upstream postgres redis
    docker compose -p sw-multi -f docker-compose.bench.yml exec -T api python scripts/budget_race_check.py --workers 4
    docker compose -p sw-multi -f docker-compose.bench.yml down -v

Needs DATABASE_URL and REDIS_URL (set in the containers) and the gateway at --url.
"""
import argparse
import asyncio
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
import redis  # noqa: E402

import budget  # noqa: E402
import db  # noqa: E402
import pricing  # noqa: E402
from pricing import MODEL_PRICES, cost_micro_usd, estimate_input_tokens  # noqa: E402
from scripts.create_project import create_project  # noqa: E402

MODEL = "gpt-4o"
MAX_TOKENS = 100
MESSAGES = [{"role": "user", "content": "Summarise the quarterly report in one line."}]


def worker_ticks() -> dict:
    """CPU ticks (utime+stime) per uvicorn worker process (multiprocessing children), from /proc."""
    ticks = {}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode(errors="replace")
            if "multiprocessing.spawn" not in cmd or "spawn_main" not in cmd:
                continue
            with open(f"/proc/{pid}/stat") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
            ticks[pid] = int(fields[11]) + int(fields[12])
        except OSError:
            continue
    return ticks


async def attempt(args) -> list:
    """One burst of --total concurrent requests against a fresh project. Returns the list of problems."""
    input_tokens = estimate_input_tokens(MESSAGES, MODEL)
    estimate = cost_micro_usd(MODEL, input_tokens, MAX_TOKENS)
    in_price, out_price = MODEL_PRICES[MODEL]
    assert estimate == input_tokens * in_price + MAX_TOKENS * out_price  # prices are whole micro-USD/token here
    budget_micro = args.fits * estimate + estimate // 2
    name = f"race-{uuid.uuid4().hex[:10]}"
    key = create_project(name, budget_micro / 1_000_000)
    with db.sync_connect() as conn:
        row = conn.execute("SELECT id, monthly_budget_usd FROM projects WHERE name = %s", (name,)).fetchone()
    project_id = row["id"]
    stored_budget = int(row["monthly_budget_usd"] * 1_000_000)   # what auth.py gives the gateway
    expected_ok = min(args.total, stored_budget // estimate)
    print(f"tokenizer: {'tiktoken' if pricing._encoding_for(MODEL) is not None else 'BYTE-COUNT FALLBACK'}; "
          f"input_tokens={input_tokens} estimate={input_tokens}*{in_price:g} + {MAX_TOKENS}*{out_price:g} = {estimate} micro-USD")
    print(f"budget stored = {stored_budget} micro-USD; {stored_budget} // {estimate} = {stored_budget // estimate} "
          f"reservations fit -> expected 200s = {expected_ok}, 429s = {args.total - expected_ok}")

    before = worker_ticks()
    body = {"model": MODEL, "messages": MESSAGES, "max_tokens": MAX_TOKENS}
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=args.total + 10)) as client:
        responses = await asyncio.gather(*[client.post(args.url, json=body, headers=headers)
                                           for _ in range(args.total)])
    after = worker_ticks()
    codes = [r.status_code for r in responses]
    ok, rejected = codes.count(200), codes.count(429)
    bad_reason = [r.headers.get("X-ShieldWall-Reason") for r in responses
                  if r.status_code == 429 and r.headers.get("X-ShieldWall-Reason") != "budget_exceeded"]

    spent_key, holds_key, _ = budget.budget_keys(project_id)
    r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    deadline = time.time() + 10
    while r.hlen(holds_key) and time.time() < deadline:   # holds are released after the response is sent
        time.sleep(0.2)
    spent, holds = int(r.get(spent_key) or 0), r.hlen(holds_key)

    problems = []
    if expected_ok != args.fits:
        problems.append(f"setup error: budget fits {expected_ok} reservations, not {args.fits}")
    if ok != expected_ok:
        problems.append(f"expected exactly {expected_ok} x 200, got {ok}")
    if rejected != args.total - expected_ok:
        problems.append(f"expected {args.total - expected_ok} x 429, got {rejected}")
    if ok + rejected != args.total:
        problems.append(f"other statuses: {sorted(set(codes) - {200, 429})}")
    if bad_reason:
        problems.append(f"{len(bad_reason)} x 429 without X-ShieldWall-Reason: budget_exceeded (got {set(bad_reason)})")
    if holds:
        problems.append(f"{holds} holds left in Redis")
    if not 0 < spent <= budget_micro:
        problems.append(f"spent {spent} micro-USD outside (0, {budget_micro}]")
    busy = [pid for pid in after if after[pid] > before.get(pid, 0)]
    print(f"worker processes found: {len(after)}; used CPU during the burst: {len(busy)}"
          + ("" if after else " (none found: single-process server)"))
    print(f"statuses: {sorted(set(codes))} 200={ok} 429={rejected}  spent={spent} budget={budget_micro} holds={holds}")
    if problems:
        return problems
    if args.workers > 1 and len(busy) < 2:
        return [f"WORKERS: only {len(busy)} of {len(after)} worker processes used CPU during the burst "
                f"(expected at least 2 with --workers {args.workers})"]
    return []


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000/v1/chat/completions")
    ap.add_argument("--total", type=int, default=50)
    ap.add_argument("--fits", type=int, default=7, help="reservations the budget has room for")
    ap.add_argument("--workers", type=int, default=1,
                    help="uvicorn workers in the stack; above 1, at least 2 must show CPU use during the burst")
    ap.add_argument("--retries", type=int, default=2,
                    help="extra attempts allowed when the ONLY problem is that too few workers served the burst")
    args = ap.parse_args()

    for n in range(1, args.retries + 2):
        print(f"attempt {n} of {args.retries + 1}")
        problems = await attempt(args)
        if not problems:
            print(f"PASS (attempts: {n})")
            return 0
        if len(problems) == 1 and problems[0].startswith("WORKERS:") and n <= args.retries:
            print("RETRY: " + problems[0])
            continue
        print(f"FAIL (attempts: {n}): " + "; ".join(problems))
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

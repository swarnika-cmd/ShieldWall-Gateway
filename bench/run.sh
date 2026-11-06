#!/usr/bin/env bash
# Gateway overhead benchmark: k6 -> mock (direct) vs k6 -> gateway -> mock.
#
#   bench/run.sh            full run: 50 and 200 RPS, 30 s each (run on an idle machine)
#   bench/run.sh --quick    smoke test: 10 RPS, 5 s
#
# Env overrides: BENCH_RATES, BENCH_DURATION, MOCK_LATENCY_MS, BENCH_CPUS_* (see
# bench/docker-compose.bench.yml), BENCH_HARDWARE (free text for the report),
# EXTRA_COMPOSE (path to an extra compose file, e.g. to mount a tokenizer cache).
# Results: bench/results/summary.md, bench/results/k6-summary.json, bench/results/db-crosscheck.txt
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "--quick" ]]; then
  export BENCH_RATES="${BENCH_RATES:-10}" BENCH_DURATION="${BENCH_DURATION:-5s}"
fi
export BENCH_RATES="${BENCH_RATES:-50,200}" BENCH_DURATION="${BENCH_DURATION:-30s}"
export BENCH_HARDWARE="${BENCH_HARDWARE:-Apple M4 Pro (12 cores), Docker Desktop Linux VM ($(docker info --format '{{.NCPU}}') vCPUs, $(docker info --format '{{.MemTotal}}' | awk '{printf "%.1f GiB", $1/1073741824}'))}"

COMPOSE=(docker compose -f docker-compose.bench.yml)
if [[ -n "${EXTRA_COMPOSE:-}" ]]; then COMPOSE+=(-f "$(cd "$(dirname "$EXTRA_COMPOSE")" && pwd)/$(basename "$EXTRA_COMPOSE")"); fi

cleanup() { "${COMPOSE[@]}" --profile load down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

mkdir -p results
echo "==> starting stack (rates: $BENCH_RATES, duration: $BENCH_DURATION)"
"${COMPOSE[@]}" up -d --build --wait api worker mock-upstream postgres redis

keys=()
for rate in ${BENCH_RATES//,/ }; do
  key=$("${COMPOSE[@]}" exec -T api python scripts/create_project.py \
        --name "bench-r${rate}" --budget-usd 100000 --quiet)
  keys+=("${rate}:${key}")
done
export BENCH_API_KEYS
BENCH_API_KEYS=$(IFS=,; echo "${keys[*]}")

echo "==> warm-up (not measured, separate project so it is not in the cross-check)"
warmup_key=$("${COMPOSE[@]}" exec -T api python scripts/create_project.py \
             --name bench-warmup --budget-usd 100 --quiet)
"${COMPOSE[@]}" exec -T api python - <<PY
import json, urllib.request
key = "${warmup_key}"
body = json.dumps({"model": "gpt-4o-mini", "max_tokens": 16,
                   "messages": [{"role": "user", "content": "warm up a@b.co"}]}).encode()
for _ in range(20):
    req = urllib.request.Request("http://localhost:8000/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    urllib.request.urlopen(req).read()
PY

echo "==> running k6"
"${COMPOSE[@]}" --profile load run --rm k6 run --quiet /scripts/gateway_overhead.js

echo "==> waiting for the Celery worker to drain the log queue"
for _ in $(seq 1 60); do
  depth=$("${COMPOSE[@]}" exec -T redis redis-cli LLEN celery | tr -d '\r')
  [[ "$depth" == "0" ]] && break
  sleep 1
done

echo "==> in-app cross-check (gateway_overhead_ms recorded by the gateway itself)"
"${COMPOSE[@]}" exec -T postgres psql -U postgres -d shieldwall -c "
  SELECT tenant_id,
         COUNT(*) AS requests,
         round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY gateway_overhead_ms)::numeric, 3) AS overhead_p50_ms,
         round(percentile_cont(0.99) WITHIN GROUP (ORDER BY gateway_overhead_ms)::numeric, 3) AS overhead_p99_ms,
         round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY upstream_ms)::numeric, 1)         AS upstream_p50_ms
  FROM request_logs WHERE tenant_id LIKE 'bench-r%' GROUP BY tenant_id ORDER BY tenant_id;" \
  | tee results/db-crosscheck.txt

{
  echo
  echo "## In-app cross-check"
  echo
  echo "gateway_overhead_ms as recorded by the gateway (handler time minus upstream wait;"
  echo "excludes HTTP parsing/serialisation done by uvicorn, so it is a lower bound):"
  echo
  echo '```'
  cat results/db-crosscheck.txt
  echo '```'
} >> results/summary.md
echo "==> done: bench/results/summary.md"

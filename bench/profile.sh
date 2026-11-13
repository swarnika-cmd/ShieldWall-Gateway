#!/usr/bin/env bash
# Profile the gateway (one uvicorn worker) under constant-arrival-rate load with py-spy.
#
#   TIKTOKEN_CACHE_HOST=/abs/dir bench/profile.sh idle      # --idle: wall-clock view (waiting included)
#   TIKTOKEN_CACHE_HOST=/abs/dir bench/profile.sh noidle    # idle samples dropped
#   TIKTOKEN_CACHE_HOST=/abs/dir bench/profile.sh gil       # only samples of the thread holding the GIL
#   TIKTOKEN_CACHE_HOST=/abs/dir bench/profile.sh none      # control: same load, no py-spy attached
#
# py-spy normally pauses the process for every sample. PROFILE_SPY_ARGS="--nonblocking" (with
# PROFILE_TAG=nb to keep the output apart) samples without pausing, at the cost of occasionally
# inconsistent stacks; use it to check that the profiler itself is not what saturates the gateway.
#
# Per run: k6 drives the gateway only (TARGETS=gateway) for PROFILE_DURATION; once the first
# request is logged, py-spy records two 60 s windows on the uvicorn worker (pid 1 in the
# container): a flame graph (SVG) and raw collapsed stacks.
# Output: bench/results/profile/<label>/  (flame.svg, stacks.txt, k6 summary, notes.txt)
# Env: PROFILE_RATE (200), PROFILE_DURATION (150s), PROFILE_PROJECT (sw-prof), PROFILE_SPY_ARGS, PROFILE_TAG, PROFILE_HZ (100),
#      UVICORN_WORKERS (1), BENCH_CPUS_* (see docker-compose.bench.yml).
set -euo pipefail
cd "$(dirname "$0")"

mode="${1:?usage: profile.sh idle|noidle|gil}"
case "$mode" in
  idle)   IDLE_FLAG=(--idle) ;;
  noidle) IDLE_FLAG=() ;;
  gil)    IDLE_FLAG=(--gil) ;;
  none)   IDLE_FLAG=() ;;
  *) echo "mode must be idle, noidle, gil or none" >&2; exit 2 ;;
esac
: "${TIKTOKEN_CACHE_HOST:?set TIKTOKEN_CACHE_HOST (see docker-compose.tokenizer-cache.yml)}"
RATE="${PROFILE_RATE:-200}"
DURATION="${PROFILE_DURATION:-150s}"
PROJECT="${PROFILE_PROJECT:-sw-prof}"
LABEL="${mode}-${RATE}rps${PROFILE_HZ:+-${PROFILE_HZ}hz}${PROFILE_TAG:+-$PROFILE_TAG}"
SPY_ARGS=(${PROFILE_SPY_ARGS:-})
OUT="results/profile/${LABEL}"

export BENCH_RATES="$RATE" BENCH_DURATION="$DURATION" BENCH_TARGETS=gateway TIKTOKEN_CACHE_HOST
export BENCH_HARDWARE="${BENCH_HARDWARE:-Apple M4 Pro (12 cores), Docker Desktop Linux VM ($(docker info --format '{{.NCPU}}') vCPUs, $(docker info --format '{{.MemTotal}}' | awk '{printf "%.1f GiB", $1/1073741824}'))}"

COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.bench.yml -f docker-compose.tokenizer-cache.yml -f docker-compose.profile.yml)
cleanup() { "${COMPOSE[@]}" --profile load down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

mkdir -p "$OUT" results/profile/k6out
echo "==> building base image and starting stack ($PROJECT)"
"${COMPOSE[@]}" build worker
"${COMPOSE[@]}" up -d --build --wait api worker mock-upstream postgres redis

key=$("${COMPOSE[@]}" exec -T api python scripts/create_project.py --name "bench-r${RATE}" --budget-usd 100000 --quiet)
export BENCH_API_KEYS="${RATE}:${key}"
warmup_key=$("${COMPOSE[@]}" exec -T api python scripts/create_project.py --name bench-warmup --budget-usd 100 --quiet)
"${COMPOSE[@]}" exec -T api python - <<PY
import json, urllib.request
body = json.dumps({"model": "gpt-4o-mini", "max_tokens": 16,
                   "messages": [{"role": "user", "content": "warm up a@b.co"}]}).encode()
for _ in range(20):
    req = urllib.request.Request("http://localhost:8000/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer ${warmup_key}"})
    urllib.request.urlopen(req).read()
PY

{
  echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "mode=$mode rate=$RATE duration=$DURATION"
  echo "hardware=$BENCH_HARDWARE"
  echo "api_cpuset=${BENCH_CPUS_API:-0-1} uvicorn_workers=${UVICORN_WORKERS:-1}"
  "${COMPOSE[@]}" exec -T api python - <<'PY'
import os
n = os.cpu_count()
print("container os.cpu_count()=%d sched_getaffinity=%d default to_thread max_workers=min(32, cpu_count+4)=%d"
      % (n, len(os.sched_getaffinity(0)), min(32, n + 4)))
PY
  "${COMPOSE[@]}" exec -T -u root api py-spy --version
} | tee "$OUT/notes.txt"

echo "==> starting k6 (gateway only, $RATE req/s, $DURATION)"
"${COMPOSE[@]}" --profile load run --rm -T k6 run --quiet /scripts/gateway_overhead.js \
  > "$OUT/k6-stdout.md" 2> "$OUT/k6-stderr.txt" &
k6_pid=$!

echo "==> waiting for the first logged gateway request"
for _ in $(seq 1 120); do
  n=$("${COMPOSE[@]}" exec -T postgres psql -U postgres -d shieldwall -tAc \
      "SELECT COUNT(*) FROM request_logs WHERE tenant_id='bench-r${RATE}'" 2>/dev/null || echo 0)
  [[ "${n:-0}" -gt 0 ]] && break
  sleep 1
done
echo "load started: $(date -u +%H:%M:%S)" | tee -a "$OUT/notes.txt"
sleep 12   # let the queue reach steady state before recording

spy() {  # spy <format> <outfile>
  "${COMPOSE[@]}" exec -T -u root api py-spy record --pid 1 --rate "${PROFILE_HZ:-100}" --subprocesses ${IDLE_FLAG[@]+"${IDLE_FLAG[@]}"} ${SPY_ARGS[@]+"${SPY_ARGS[@]}"} \
    --threads --format "$1" -o "/out/${LABEL}/$2" --duration 60
}

if [[ "$mode" != none ]]; then
echo "==> py-spy window 1: flamegraph" | tee -a "$OUT/notes.txt"
mkdir -p "$OUT"
"${COMPOSE[@]}" exec -T -u root api sh -c "mkdir -p /out/${LABEL}"
spy flamegraph flame.svg
"${COMPOSE[@]}" exec -T -u root api py-spy dump --pid 1 > "$OUT/py-spy-dump.txt" 2>&1 || true
docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' \
  $("${COMPOSE[@]}" ps -q api worker mock-upstream redis postgres) | tee -a "$OUT/notes.txt"
echo "==> py-spy window 2: raw collapsed stacks" | tee -a "$OUT/notes.txt"
spy raw stacks.txt
echo "window 2 done: $(date -u +%H:%M:%S)" | tee -a "$OUT/notes.txt"

fi

echo "==> waiting for k6 to finish"
wait "$k6_pid" || true
cp results/profile/k6out/summary.md "$OUT/k6-summary.md" 2>/dev/null || true
cp results/profile/k6out/k6-summary.json "$OUT/k6-summary.json" 2>/dev/null || true
echo "==> done: bench/results/profile/${LABEL}/"

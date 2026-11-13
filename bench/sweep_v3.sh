#!/usr/bin/env bash
# Final benchmark for the sniffio install / upstream pool limits. Run it on an idle machine.
#
#   TIKTOKEN_CACHE_HOST=/abs/dir/with/tiktoken-cache bench/sweep_v3.sh          # all parts (A, R, B, P)
#   TIKTOKEN_CACHE_HOST=... bench/sweep_v3.sh A                                  # one part: A | B | R | P
#   DRY_RUN=1 TIKTOKEN_CACHE_HOST=... bench/sweep_v3.sh                          # plan + estimate + builds + 10 s smoke runs
#
# Variants (all use the same code; they differ in the image and the upstream pool limits):
#   before : image v3-nosniffio (sniffio removed, as before the requirements pin), pool 500/100
#   after  : image v3-fixed (sniffio==1.3.1 installed),                           pool 500/100
#   alt    : image v3-fixed,                                                       pool 100/100
# Part A  1 worker. before and after at A_RATES (150 200 250 300); alt only at ALT_RATES (200 250).
#         REPS repetitions (3) per (variant, rate), interleaved: for each rep, for each rate, every variant in turn,
#         with the variant order rotated per rep (rep1 before/after/alt, rep2 after/alt/before, rep3 alt/before/after;
#         rotated two-way where there is no alt), so machine drift and run order hit all variants alike.
# Part R  scripts/budget_race_check.py against an N-worker stack (3 checks), result in budget-race.txt.
# Part B  "after" with N workers (N = CPUs in BENCH_CPUS_API, default 0-1, so N = 2) at B_RATES (150 200 300 400),
#         REPS repetitions. The 1-worker "after" run and the N-worker run at each rate are adjacent within each rep
#         (order swapped on even reps), and the 1-worker runs are repeated here (not reused from part A), so the
#         scaling pairs are close in time.
# Part P  py-spy (--gil, 100 Hz, 60 s windows: one flame graph, one raw stacks) at 50 req/s, 1 worker, for before and after.
#         Writes docs/profiling/flame-1worker-50rps-{before,after}.svg, stacks-1worker-50rps-*.txt.gz and
#         docs/profiling/analysis/gil-50rps-{before,after}.md (bucket tables from bench/analyze_stacks.py).
#
# Only the API image varies between variants; the Celery worker and the mock upstream always run v3-fixed; k6 is pinned
# to grafana/k6:0.54.0 and its image id is recorded in meta.txt.
# Every run: fresh stack (compose project sw-v3), k6 against the gateway only (constant arrival rate) for
# SWEEP_DURATION, in-app cross-check from Postgres, teardown, SWEEP_COOLDOWN seconds of rest. meta.txt per run records
# date, host, Docker CPUs/RAM, API cpuset, workers, image id, loaded pool limits, whether sniffio imports, httpcore
# version, mock latency, k6 settings, load average. Runs are resumable: a label with k6-summary.json is skipped
# (SWEEP_FORCE=1 redoes everything): a run counts as done only when its directory has a .done marker, written after the
# stack was torn down and the cross-check saved.
#
# Time: the script prints an estimate at start (about 2h17m for all parts). Budget about 2h30m: collapsed runs take
# longer than healthy ones (k6 graceful stop, Celery queue drain before the cross-check).
#
# Healthy run (used by summary.md): error rate < 1% AND dropped iterations = 0 AND gateway p95 < 2 x MOCK_LATENCY_MS
# (400 ms with the default 200 ms mock).
#
# Env: SWEEP_DURATION (60s), SWEEP_COOLDOWN (30), SWEEP_REPS (3), SWEEP_A_RATES, SWEEP_ALT_RATES, SWEEP_B_RATES,
#      SWEEP_OUT (bench/results/sweep-v3), SWEEP_RACE ("workers:cpuset ...", default "N:$BENCH_CPUS_API"),
#      BENCH_CPUS_API (0-1), MOCK_LATENCY_MS (200), BENCH_CPUS_* as in docker-compose.bench.yml,
#      RUN_OVERHEAD_S (45, only for the time estimate), BENCH_HARDWARE (free text).
set -euo pipefail
cd "$(dirname "$0")"

PART="${1:-all}"
DRY_RUN="${DRY_RUN:-0}"
DURATION="${SWEEP_DURATION:-60s}"
COOLDOWN="${SWEEP_COOLDOWN:-30}"
REPS="${SWEEP_REPS:-3}"
A_RATES="${SWEEP_A_RATES:-150 200 250 300}"
ALT_RATES="${SWEEP_ALT_RATES:-200 250}"
B_RATES="${SWEEP_B_RATES:-150 200 300 400}"
P_RATE=50
P_LOAD="${SWEEP_P_LOAD:-150s}"; P_WINDOW="${SWEEP_P_WINDOW:-60}"; P_SETTLE="${SWEEP_P_SETTLE:-12}"
RUN_OVERHEAD_S="${RUN_OVERHEAD_S:-45}"
MOCK_LATENCY="${MOCK_LATENCY_MS:-200}"
CPUS_API="${BENCH_CPUS_API:-0-1}"
PROJECT=sw-v3
case "$PART" in all|A|B|R|P) ;; *) echo "part must be all, A, B, R or P" >&2; exit 2 ;; esac

count_cpus() {  # "0-1" -> 2, "0,2,4-5" -> 4
  echo "$1" | tr ',' '\n' | awk -F- '{ if (NF == 2) n += $2 - $1 + 1; else n += 1 } END { print n }'
}
N_WORKERS="$(count_cpus "$CPUS_API")"
RACE_SPECS="${SWEEP_RACE:-${N_WORKERS}:${CPUS_API}}"

OUT_REL="${SWEEP_OUT:-results/sweep-v3}"
mkdir -p "$OUT_REL"; OUT="$(cd "$OUT_REL" && pwd)"
REPO="$(cd .. && pwd)"
DOCS="$REPO/docs/profiling"

# ---------------------------------------------------------------- pre-flight (fail fast, before anything timed)
preflight() {
  : "${TIKTOKEN_CACHE_HOST:?set TIKTOKEN_CACHE_HOST (see docker-compose.tokenizer-cache.yml)}"
  for f in 9b5ad71b2ce5302211f9c61530b329a4922fc6a4 fb374d419588a4632f3f557e76b4b70aebbca790; do
    [[ -s "$TIKTOKEN_CACHE_HOST/$f" ]] || { echo "tiktoken cache incomplete: $TIKTOKEN_CACHE_HOST/$f missing" >&2; exit 1; }
  done
  docker info >/dev/null 2>&1 || { echo "docker daemon not reachable" >&2; exit 1; }
  local ncpu; ncpu="$(docker info --format '{{.NCPU}}')"
  local max_cpu; max_cpu="$(echo "$CPUS_API" | tr ',-' '\n\n' | sort -n | tail -1)"
  [[ "$max_cpu" -lt "$ncpu" ]] || { echo "BENCH_CPUS_API=$CPUS_API exceeds the $ncpu CPUs Docker has" >&2; exit 1; }
  for img in postgres:16 redis:7 python:3.11-slim grafana/k6:0.54.0; do
    docker image inspect "$img" >/dev/null 2>&1 || { echo "image $img not present locally" >&2; exit 1; }
  done
}
export TIKTOKEN_CACHE_HOST="${TIKTOKEN_CACHE_HOST:-}"
export BENCH_HARDWARE="${BENCH_HARDWARE:-Apple M4 Pro (12 cores), Docker Desktop Linux VM ($(docker info --format '{{.NCPU}}' 2>/dev/null) vCPUs, $(docker info --format '{{.MemTotal}}' 2>/dev/null | awk '{printf "%.1f GiB", $1/1073741824}'))}"

# ---------------------------------------------------------------- plan
PLAN=()   # "part|variant|workers|rate|rep"
add_plan() {
  local e="$1|$2|$3|$4|$5" x
  for x in ${PLAN[@]+"${PLAN[@]}"}; do [[ "$x" == "$e" ]] && return 0; done
  PLAN+=("$e")
}
in_list() { local x; for x in $2; do [[ "$x" == "$1" ]] && return 0; done; return 1; }
rotated_variants() {  # rotated_variants <rep> <with_alt 0|1>  -> variant order for this rep
  local list=(before after) k
  [[ "$2" == 1 ]] && list=(before after alt)
  local n=${#list[@]} shift_by=$(( ($1 - 1) % ${#list[@]} )) out=""
  for ((k = 0; k < n; k++)); do out="$out ${list[$(( (k + shift_by) % n ))]}"; done
  echo "$out"
}
make_plan() {
  local rep rate v
  if [[ "$PART" == all || "$PART" == A ]]; then
    for rep in $(seq 1 "$REPS"); do
      for rate in $A_RATES; do
        if in_list "$rate" "$ALT_RATES"; then
          for v in $(rotated_variants "$rep" 1); do add_plan A "$v" 1 "$rate" "$rep"; done
        else
          for v in $(rotated_variants "$rep" 0); do add_plan A "$v" 1 "$rate" "$rep"; done
        fi
      done
    done
  fi
  if [[ "$PART" == all || "$PART" == B ]]; then
    for rep in $(seq 1 "$REPS"); do
      for rate in $B_RATES; do
        if (( rep % 2 == 1 )); then
          add_plan B after 1 "$rate" "$rep"; add_plan B after "$N_WORKERS" "$rate" "$rep"
        else
          add_plan B after "$N_WORKERS" "$rate" "$rep"; add_plan B after 1 "$rate" "$rep"
        fi
      done
    done
  fi
}
variant_cfg() {  # sets V_IMAGE V_MC V_MK
  case "$1" in
    before) V_IMAGE=shieldwall-gateway:v3-nosniffio; V_MC=500; V_MK=100 ;;
    after)  V_IMAGE=shieldwall-gateway:v3-fixed;     V_MC=500; V_MK=100 ;;
    alt)    V_IMAGE=shieldwall-gateway:v3-fixed;     V_MC=100; V_MK=100 ;;
    *) echo "unknown variant $1" >&2; exit 2 ;;
  esac
}
label_of() { echo "$1-$2-$3w-r$4-rep$5"; }   # part variant workers rate rep

estimate() {
  local secs=0 d=${DURATION%s} n_runs=${#PLAN[@]} n_race=0 spec
  secs=$(( n_runs * (d + COOLDOWN + RUN_OVERHEAD_S) ))
  if [[ "$PART" == all || "$PART" == R || "$PART" == B ]]; then
    for spec in $RACE_SPECS; do n_race=$((n_race + 1)); done
    secs=$(( secs + n_race * (3 * 10 + COOLDOWN + RUN_OVERHEAD_S) ))
  fi
  if [[ "$PART" == all || "$PART" == P ]]; then secs=$(( secs + 2 * (${P_LOAD%s} + COOLDOWN + RUN_OVERHEAD_S + 30) )); fi
  secs=$(( secs + 300 ))   # image builds, summary
  echo "$secs"
}
print_plan() {
  local i=0 e p v w r k secs
  echo "Part $PART: ${#PLAN[@]} load runs$( [[ "$PART" == all || "$PART" == R || "$PART" == B ]] && echo " + race checks ($RACE_SPECS)")$( [[ "$PART" == all || "$PART" == P ]] && echo " + 2 py-spy runs (50 req/s)")"
  for e in ${PLAN[@]+"${PLAN[@]}"}; do
    i=$((i + 1)); IFS='|' read -r p v w r k <<< "$e"
    printf '  %3d. %-30s part=%s variant=%-6s workers=%s rate=%s rep=%s\n' "$i" "$(label_of "$p" "$v" "$w" "$r" "$k")" "$p" "$v" "$w" "$r" "$k"
  done
  secs="$(estimate)"
  echo "Settings: k6 ${DURATION} per run, cool-down ${COOLDOWN}s, mock latency ${MOCK_LATENCY} ms, API cpuset ${CPUS_API}, N=${N_WORKERS}."
  echo "Healthy run = errors < 1% AND dropped iterations = 0 AND p95 < $((2 * MOCK_LATENCY)) ms."
  echo "Estimated total time: ${secs}s = $((secs / 60)) min (about $((secs / 3600))h$(( (secs % 3600) / 60 ))m), assuming ${RUN_OVERHEAD_S}s of stack start/warm-up/teardown per run."
}

# ---------------------------------------------------------------- stack helpers
EXTRA_F=()
dc() { docker compose -p "$PROJECT" -f docker-compose.bench.yml -f docker-compose.v3.yml ${EXTRA_F[@]+"${EXTRA_F[@]}"} "$@"; }
stop_stack() { SW_IMAGE="${SW_IMAGE:-x}" SW_SPY_OUT="${SW_SPY_OUT:-/tmp}" dc --profile load down -v --remove-orphans >/dev/null 2>&1 || true; }
trap stop_stack EXIT

build_images() {
  echo "==> building images (all of them before any timed run)"
  docker build -q -t shieldwall-gateway:v3-fixed "$REPO" >/dev/null
  docker build -q -f Dockerfile.nosniffio --build-arg BASE_IMAGE=shieldwall-gateway:v3-fixed -t shieldwall-gateway:v3-nosniffio . >/dev/null
  if [[ "$PART" == all || "$PART" == P || "$DRY_RUN" == 1 ]]; then
    docker build -q -f Dockerfile.profile --build-arg BASE_IMAGE=shieldwall-gateway:v3-nosniffio -t shieldwall-gateway:v3-before-spy . >/dev/null
    docker build -q -f Dockerfile.profile --build-arg BASE_IMAGE=shieldwall-gateway:v3-fixed -t shieldwall-gateway:v3-after-spy . >/dev/null
  fi
  docker image inspect shieldwall-gateway:v3-fixed shieldwall-gateway:v3-nosniffio >/dev/null
}

start_stack() {  # start_stack <image> <mc> <mk> <workers> <cpuset> <mock_latency> <k6out>
  export SW_IMAGE="$1" SW_MAX_CONN="$2" SW_MAX_KEEP="$3" UVICORN_WORKERS="$4" BENCH_CPUS_API="$5" MOCK_LATENCY_MS="$6" SW_K6_OUT="$7"
  mkdir -p "$7"
  dc up -d --no-build --wait api worker mock-upstream postgres redis
}

# Verifies the running api container really has what the variant claims; writes the facts to meta.txt.
check_runtime() {  # check_runtime <dir> <variant> <mc> <mk> <workers>
  local facts
  facts="$(dc exec -T api python -c "
import importlib.util, httpcore, config, os
print('sniffio_installed=' + ('yes' if importlib.util.find_spec('sniffio') else 'no'))
print('httpcore_version=' + httpcore.__version__)
print('loaded_pool_max_connections=%d' % config.UPSTREAM_MAX_CONNECTIONS)
print('loaded_pool_max_keepalive=%d' % config.UPSTREAM_MAX_KEEPALIVE)
" | tr -d '\r')"
  echo "$facts" >> "$1/meta.txt"
  local want_sniffio=yes; [[ "$2" == before ]] && want_sniffio=no
  grep -q "^sniffio_installed=$want_sniffio$" <<< "$facts" || { echo "ABORT: variant $2 expects sniffio_installed=$want_sniffio" >&2; echo "$facts" >&2; exit 1; }
  grep -q "^loaded_pool_max_connections=$3$" <<< "$facts" || { echo "ABORT: pool max connections is not $3" >&2; exit 1; }
  grep -q "^loaded_pool_max_keepalive=$4$" <<< "$facts" || { echo "ABORT: pool keepalive is not $4" >&2; exit 1; }
  grep -q "^httpcore_version=1.0.9$" <<< "$facts" || { echo "ABORT: httpcore is not 1.0.9" >&2; exit 1; }
  local n; n="$(dc exec -T api sh -c 'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline; echo; done | grep -c "multiprocessing.spawn import [s]pawn_main"' | tr -d '\r' || true)"
  echo "worker_processes_seen=${n:-0} (0 = single in-process server)" >> "$1/meta.txt"
  if (( $5 > 1 )) && [[ "${n:-0}" != "$5" ]]; then
    echo "ABORT: expected $5 uvicorn worker processes, found ${n:-0}" >&2; exit 1
  fi
}

write_meta() {  # write_meta <dir> <variant> <rep> <image> <mc> <mk> <workers> <cpuset> <rate> <duration> <part>
  local rate_vus=$(( $9 > 10 ? $9 : 10 ))
  {
    echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host=$(uname -srm); $BENCH_HARDWARE"
    echo "docker_cpus=$(docker info --format '{{.NCPU}}')"
    echo "docker_mem_bytes=$(docker info --format '{{.MemTotal}}')"
    echo "part=${11}"
    echo "variant=$2"
    echo "rep=$3"
    echo "image=$4"
    echo "image_id=$(docker image inspect --format '{{.Id}}' "$4")"
    echo "worker_and_mock_image=shieldwall-gateway:v3-fixed id=$(docker image inspect --format '{{.Id}}' shieldwall-gateway:v3-fixed)"
    echo "k6_image=grafana/k6:0.54.0 id=$(docker image inspect --format '{{.Id}}' grafana/k6:0.54.0)"
    echo "upstream_max_connections=$5"
    echo "upstream_max_keepalive=$6"
    echo "uvicorn_workers=$7"
    echo "api_container_cpuset=$8"
    echo "mock_latency_ms=$MOCK_LATENCY"
    echo "k6=executor=constant-arrival-rate rate=${9}/s duration=${10} preAllocatedVUs=$rate_vus maxVUs=$(( $9 * 4 )) targets=gateway"
    echo "load_average_before=$(uptime | sed 's/.*load averages*: //')"
  } > "$1/meta.txt"
}

new_project() {  # new_project <rate> -> sets KEY, runs the warm-up
  KEY=$(dc exec -T api python scripts/create_project.py --name "bench-r$1" --budget-usd 100000 --quiet)
  local warm
  warm=$(dc exec -T api python scripts/create_project.py --name bench-warmup --budget-usd 100 --quiet)
  dc exec -T api python - <<PY
import json, urllib.request
body = json.dumps({"model": "gpt-4o-mini", "max_tokens": 16,
                   "messages": [{"role": "user", "content": "warm up a@b.co"}]}).encode()
for _ in range(100):
    req = urllib.request.Request("http://localhost:8000/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer ${warm}"})
    urllib.request.urlopen(req).read()
PY
}

crosscheck() {  # crosscheck <dir> <rate>
  local depth="?"
  for _ in $(seq 1 120); do   # let the Celery worker drain so the cross-check sees every row
    depth=$(dc exec -T redis redis-cli LLEN celery | tr -d '\r')
    [[ "$depth" == "0" ]] && break
    sleep 1
  done
  echo "celery_queue_depth_after_wait=$depth" >> "$1/meta.txt"
  dc exec -T postgres psql -U postgres -d shieldwall -c "
    SELECT tenant_id, COUNT(*) AS requests,
           round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY gateway_overhead_ms)::numeric, 3) AS overhead_p50_ms,
           round(percentile_cont(0.99) WITHIN GROUP (ORDER BY gateway_overhead_ms)::numeric, 3) AS overhead_p99_ms,
           round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY upstream_ms)::numeric, 1)         AS upstream_p50_ms
    FROM request_logs WHERE tenant_id = 'bench-r$2' GROUP BY tenant_id;" > "$1/db-crosscheck.txt"
}

run_one() {  # run_one <part> <variant> <workers> <rate> <rep> [<label>]
  local part="$1" v="$2" workers="$3" rate="$4" rep="$5"
  local label="${6:-$(label_of "$1" "$2" "$3" "$4" "$5")}" dir
  dir="$OUT/$label"
  if [[ -f "$dir/.done" && "${SWEEP_FORCE:-0}" != 1 ]]; then echo "==> $label: already done (.done marker), skipping"; return 0; fi
  variant_cfg "$v"
  echo "==> $label: image=$V_IMAGE pool=$V_MC/$V_MK workers=$workers cpuset=$CPUS_API rate=$rate duration=$DURATION"
  rm -rf "$dir"; mkdir -p "$dir"
  EXTRA_F=()
  write_meta "$dir" "$v" "$rep" "$V_IMAGE" "$V_MC" "$V_MK" "$workers" "$CPUS_API" "$rate" "$DURATION" "$part"
  start_stack "$V_IMAGE" "$V_MC" "$V_MK" "$workers" "$CPUS_API" "$MOCK_LATENCY" "$dir"
  check_runtime "$dir" "$v" "$V_MC" "$V_MK" "$workers"
  new_project "$rate"
  ( sleep $(( ${DURATION%s} / 2 )); docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' \
      $(dc ps -q api worker mock-upstream redis postgres) > "$dir/api-stats.txt" 2>&1 || true ) &
  local stats_pid=$!
  BENCH_RATES="$rate" BENCH_DURATION="$DURATION" BENCH_TARGETS=gateway BENCH_API_KEYS="${rate}:${KEY}" \
    dc --profile load run --rm -T k6 run --quiet /scripts/gateway_overhead.js \
    > "$dir/k6-stdout.md" 2> "$dir/k6-stderr.txt" || true
  wait "$stats_pid" || true
  mv "$dir/summary.md" "$dir/k6-summary.md" 2>/dev/null || true
  [[ -s "$dir/k6-summary.json" ]] || { echo "ABORT: k6 produced no summary for $label (see $dir/k6-stderr.txt)" >&2; exit 1; }
  crosscheck "$dir" "$rate"
  stop_stack
  touch "$dir/.done"
  echo "==> $label done; cooling down ${COOLDOWN}s"
  sleep "$COOLDOWN"
}

# py-spy run, --gil mode: flame graph (window 1) and raw stacks (window 2) at 50 req/s, one worker.
profile_one() {  # profile_one <variant> <docs_dir>
  local v="$1" dest="$2" label="P-$1-1w-r${P_RATE}" dir
  dir="$OUT/$label"
  variant_cfg "$v"
  echo "==> $label: py-spy --gil, ${P_WINDOW}s windows, load ${P_LOAD}"
  rm -rf "$dir"; mkdir -p "$dir/spy"
  EXTRA_F=(-f docker-compose.v3-spy.yml)
  write_meta "$dir" "$v" 1 "shieldwall-gateway:v3-$v-spy" "$V_MC" "$V_MK" 1 "$CPUS_API" "$P_RATE" "$P_LOAD" P
  export SW_SPY_OUT="$dir/spy"
  start_stack "shieldwall-gateway:v3-$v-spy" "$V_MC" "$V_MK" 1 "$CPUS_API" "$MOCK_LATENCY" "$dir"
  check_runtime "$dir" "$v" "$V_MC" "$V_MK" 1
  new_project "$P_RATE"
  BENCH_RATES="$P_RATE" BENCH_DURATION="$P_LOAD" BENCH_TARGETS=gateway BENCH_API_KEYS="${P_RATE}:${KEY}" \
    dc --profile load run --rm -T k6 run --quiet /scripts/gateway_overhead.js \
    > "$dir/k6-stdout.md" 2> "$dir/k6-stderr.txt" &
  local k6_pid=$!
  local n=0
  for _ in $(seq 1 120); do
    n=$(dc exec -T postgres psql -U postgres -d shieldwall -tAc "SELECT COUNT(*) FROM request_logs WHERE tenant_id='bench-r${P_RATE}'" 2>/dev/null || echo 0)
    [[ "${n:-0}" -gt 0 ]] && break
    sleep 1
  done
  sleep "$P_SETTLE"
  dc exec -T -u root api py-spy record --pid 1 --rate 100 --subprocesses --gil --threads --format flamegraph \
      -o /out/flame.svg --duration "$P_WINDOW" || true
  dc exec -T -u root api py-spy dump --pid 1 > "$dir/py-spy-dump.txt" 2>&1 || true
  dc exec -T -u root api py-spy record --pid 1 --rate 100 --subprocesses --gil --threads --format raw \
      -o /out/stacks.txt --duration "$P_WINDOW" || true
  docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' $(dc ps -q api) > "$dir/api-stats.txt" 2>&1 || true
  wait "$k6_pid" || true
  mv "$dir/summary.md" "$dir/k6-summary.md" 2>/dev/null || true
  [[ -s "$dir/spy/flame.svg" && -s "$dir/spy/stacks.txt" ]] || { echo "ABORT: py-spy produced no output for $label" >&2; exit 1; }
  crosscheck "$dir" "$P_RATE"
  stop_stack
  touch "$dir/.done"
  EXTRA_F=()
  mkdir -p "$dest/analysis"
  cp "$dir/spy/flame.svg" "$dest/flame-1worker-50rps-$v.svg"
  gzip -c "$dir/spy/stacks.txt" > "$dest/stacks-1worker-50rps-$v.txt.gz"
  docker run --rm -v "$dir/spy":/in:ro -v "$PWD/analyze_stacks.py":/a.py:ro python:3.11-slim \
    python -I /a.py /in/stacks.txt --title "gil-50rps-$v ($label)" > "$dest/analysis/gil-50rps-$v.md"
  echo "==> $label done; outputs in $dest; cooling down ${COOLDOWN}s"
  sleep "$COOLDOWN"
}

race_one() {  # race_one <workers> <cpuset>
  local workers="$1" cpuset="$2"
  echo "==> budget race check: $workers workers, cpuset $cpuset"
  EXTRA_F=()
  start_stack shieldwall-gateway:v3-fixed 500 100 "$workers" "$cpuset" 800 "$OUT/k6out"
  {
    echo "# provenance: bench/sweep_v3.sh part R; host: $(uname -srm); $BENCH_HARDWARE; Docker $(docker info --format '{{.NCPU}}') CPUs"
    echo "# command: SWEEP_RACE=\"$RACE_SPECS\" bench/sweep_v3.sh $PART  (this check: dc exec -T api python scripts/budget_race_check.py --workers $workers)"
    echo "== ${workers}-workers: uvicorn_workers=$workers api_cpuset=$cpuset mock_latency_ms=800 date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    for i in 1 2 3; do
      dc exec -T api python scripts/budget_race_check.py --workers "$workers" && echo "exit=0" || echo "exit=$?"
    done
  } | tee -a "$OUT/budget-race.txt"
  stop_stack
  sleep "$COOLDOWN"
}

summarise() {  # summarise <dir>
  docker run --rm -v "$1":/out -v "$PWD/sweep_summary.py":/sweep_summary.py:ro python:3.11-slim \
    python -I /sweep_summary.py /out > /dev/null
  echo "==> summary: $1/summary.md"
}

# ---------------------------------------------------------------- main
make_plan
print_plan

if [[ "$DRY_RUN" == 1 ]]; then
  preflight
  build_images
  OUT="$OUT/dry-run"; mkdir -p "$OUT"
  DURATION=10s; COOLDOWN=3; P_LOAD=40s; P_WINDOW=5; P_SETTLE=3
  echo "==> DRY RUN: one ${DURATION} smoke run at ${P_RATE} req/s per variant (output $OUT, not part of the sweep)"
  for v in before after alt; do run_one S "$v" 1 "$P_RATE" 0 "smoke-$v"; done
  run_one S after "$N_WORKERS" "$P_RATE" 0 "smoke-after-${N_WORKERS}w"
  race_one "$N_WORKERS" "$CPUS_API"
  profile_one after "$OUT/docs-preview"
  rm -rf "$OUT/k6out"
  summarise "$OUT"
  echo "==> DRY RUN finished: the plan above is what a real run executes."
  exit 0
fi

preflight
build_images
if [[ "$PART" == all || "$PART" == R ]]; then rm -f "$OUT/budget-race.txt"; fi
for e in ${PLAN[@]+"${PLAN[@]}"}; do
  IFS='|' read -r p v w r k <<< "$e"
  run_one "$p" "$v" "$w" "$r" "$k"
done
if [[ "$PART" == all || "$PART" == R || "$PART" == B ]]; then
  for spec in $RACE_SPECS; do race_one "${spec%%:*}" "${spec#*:}"; done
fi
if [[ "$PART" == all || "$PART" == P ]]; then
  profile_one before "$DOCS"
  profile_one after "$DOCS"
fi
rm -rf "$OUT/k6out"
summarise "$OUT"

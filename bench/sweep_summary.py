"""Build summary.md and summary.json for a bench/sweep_v3.sh output directory.

    python sweep_summary.py <dir>   # reads <dir>/*/{meta.txt,k6-summary.json,db-crosscheck.txt,api-stats.txt}

Healthy run: error rate < 1% AND dropped iterations = 0 AND gateway p95 < 2 x mock latency.
Per (variant, workers, rate) group the table gives how many runs were healthy, the median p50/p95/p99
over the healthy runs only and, separately, over the unhealthy runs only. Healthy and unhealthy runs are
never mixed in one statistic. Every run is listed in the raw table.
Latencies are k6 http_req_duration of the gateway scenario; the mock adds a fixed latency, so the floor
is about that value. "Completed" is requests k6 finished; "dropped" is k6 dropped_iterations (arrivals it
could not start because all VUs were busy). In-app overhead is gateway_overhead_ms from Postgres.
Runs named P-* (py-spy attached) are listed apart and excluded from the groups.
"""
import json
import os
import re
import statistics
import sys

VARIANT_ORDER = {"before": 0, "after": 1, "alt": 2}


def read_meta(path):
    meta = {}
    with open(path) as fh:
        for line in fh:
            if "=" in line:
                k, _, v = line.partition("=")
                meta.setdefault(k.strip(), v.strip())
    return meta


def crosscheck(path):
    try:
        for line in open(path):
            cols = [c.strip() for c in line.split("|")]
            if len(cols) >= 5 and cols[0].startswith("bench-r"):
                return cols[2], cols[3]
    except OSError:
        pass
    return "n/a", "n/a"


def api_cpu(path):
    try:
        for line in open(path):
            m = re.search(r"-api-1 cpu=([\d.]+)%", line)
            if m:
                return m.group(1) + "%"
    except OSError:
        pass
    return "n/a"


def fmt(v):
    return "n/a" if v is None else f"{v:.1f}"


def med(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return statistics.median(vals) if vals else None


def triple(rows):
    if not rows:
        return "none"
    return " / ".join(fmt(med(rows, k)) for k in ("p50", "p95", "p99"))


def load_runs(root):
    runs = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isfile(os.path.join(d, "k6-summary.json")):
            continue
        meta = read_meta(os.path.join(d, "meta.txt"))
        with open(os.path.join(d, "k6-summary.json")) as fh:
            r = json.load(fh)["rows"][0]
        mock = float(meta.get("mock_latency_ms", "200"))
        err = r["gateway_error_rate"] if r["gateway_error_rate"] is not None else 1.0
        dropped = r.get("dropped_iterations", 0)
        p95 = r["gateway_p95_ms"]
        healthy = err < 0.01 and dropped == 0 and p95 is not None and p95 < 2 * mock
        dur = int(re.search(r"duration=(\d+)s", meta.get("k6", "duration=0s")).group(1))
        o50, o99 = crosscheck(os.path.join(d, "db-crosscheck.txt"))
        runs.append(dict(
            name=name, meta=meta, part=meta.get("part", "?"), variant=meta.get("variant", "?"), rep=meta.get("rep", "?"),
            workers=int(meta.get("uvicorn_workers", "1")), rate=r["rate_rps"], mock=mock,
            p50=r["gateway_p50_ms"], p95=p95, p99=r["gateway_p99_ms"], err=err, dropped=dropped,
            done=r["gateway_requests"], dur=dur, healthy=healthy, o50=o50, o99=o99,
            cpu=api_cpu(os.path.join(d, "api-stats.txt")), load=meta.get("load_average_before", "?"),
            profiled=name.startswith("P-")))
    return runs


def main(root):
    runs = load_runs(root)
    sweep = [r for r in runs if not r["profiled"]]
    prof = [r for r in runs if r["profiled"]]
    out = ["# Sweep summary", ""]
    if sweep or runs:
        m = (sweep or runs)[0]["meta"]
        out += [f"Date (UTC) of first run: {m.get('date_utc')}  ", f"Host: {m.get('host')}  ",
                f"Docker: {m.get('docker_cpus')} CPUs, {m.get('docker_mem_bytes')} bytes memory  ",
                f"Mock upstream latency: {m.get('mock_latency_ms')} ms; k6: {m.get('k6')}  ", ""]
        thr = 2 * (sweep or runs)[0]["mock"]
        out += [f"Healthy run = error rate < 1% AND dropped iterations = 0 AND p95 < {thr:.0f} ms (2 x mock latency).", ""]

    groups = {}
    for r in sweep:
        groups.setdefault((r["part"], r["variant"], r["workers"], r["rate"]), []).append(r)
    keys = sorted(groups, key=lambda k: (k[0], k[3], k[2], VARIANT_ORDER.get(k[1], 9)))
    summary = {}
    out += ["## Per configuration", "",
            "| Part | Variant | Workers | Rate | Healthy runs | Healthy runs: median p50 / p95 / p99 (ms) | Unhealthy runs: median p50 / p95 / p99 (ms) | Unhealthy runs: median errors, median dropped |",
            "|---|---|---:|---:|---|---|---|---|"]
    for k in keys:
        rs = groups[k]
        good = [r for r in rs if r["healthy"]]
        bad = [r for r in rs if not r["healthy"]]
        bad_extra = (f"{statistics.median([r['err'] for r in bad]) * 100:.2f}%, {statistics.median([r['dropped'] for r in bad]):.0f}"
                     if bad else "-")
        out.append(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {len(good)} of {len(rs)} | {triple(good)} | {triple(bad)} | {bad_extra} |")
        summary[f"{k[0]}-{k[1]}-{k[2]}w-r{k[3]}"] = dict(
            runs=len(rs), healthy=len(good),
            healthy_median=dict(p50=med(good, "p50"), p95=med(good, "p95"), p99=med(good, "p99")) if good else None,
            unhealthy_median=dict(p50=med(bad, "p50"), p95=med(bad, "p95"), p99=med(bad, "p99"),
                                  error_rate=statistics.median([r["err"] for r in bad]),
                                  dropped=statistics.median([r["dropped"] for r in bad])) if bad else None)

    # scaling: part B, variant after, 1 worker vs N workers (runs paired in time within each rep)
    ws = sorted({k[2] for k in keys if k[0] == "B" and k[1] == "after"})
    if len(ws) > 1:
        out += ["", "## Scaling (part B, variant after, pool 500/100; 1- and N-worker runs adjacent in time within each rep)", "",
                "| Rate | " + " | ".join(f"{w} worker(s): healthy runs; healthy median p50 / p95 / p99 (ms)" for w in ws) + " |",
                "|---:|" + "|".join("---" for _ in ws) + "|"]
        for rate in sorted({k[3] for k in keys if k[0] == "B" and k[1] == "after"}):
            cells = []
            for w in ws:
                rs = groups.get(("B", "after", w, rate), [])
                good = [r for r in rs if r["healthy"]]
                cells.append(f"{len(good)} of {len(rs)}; {triple(good)}" if rs else "not run")
            out.append(f"| {rate} | " + " | ".join(cells) + " |")

    out += ["", "## Every run", "",
            "| Run | Rate | Healthy | p50 / p95 / p99 (ms) | Errors | Dropped | Completed (per s) | In-app overhead p50 / p99 (ms) | API CPU mid-run | Load avg before |",
            "|---|---:|---|---|---:|---:|---|---|---|---|"]
    for r in sorted(sweep, key=lambda r: r["name"]):
        out.append(f"| {r['name']} | {r['rate']} | {'yes' if r['healthy'] else 'no'} | {fmt(r['p50'])} / {fmt(r['p95'])} / {fmt(r['p99'])} "
                   f"| {r['err'] * 100:.2f}% | {r['dropped']} | {r['done']} ({r['done'] / r['dur']:.0f}) | {r['o50']} / {r['o99']} | {r['cpu']} | {r['load']} |")
    if prof:
        out += ["", "## py-spy runs (k6 outcome with the profiler attached)", "",
                "| Run | Rate | p50 / p95 / p99 (ms) | Errors | Dropped | API CPU |", "|---|---:|---|---:|---:|---|"]
        for r in prof:
            out.append(f"| {r['name']} | {r['rate']} | {fmt(r['p50'])} / {fmt(r['p95'])} / {fmt(r['p99'])} | {r['err'] * 100:.2f}% | {r['dropped']} | {r['cpu']} |")
    race = os.path.join(root, "budget-race.txt")
    if os.path.exists(race):
        out += ["", "## Budget race check", "", "```", open(race).read().rstrip(), "```"]
    out.append("")
    with open(os.path.join(root, "summary.md"), "w") as fh:
        fh.write("\n".join(out))
    with open(os.path.join(root, "summary.json"), "w") as fh:
        json.dump(dict(healthy_definition="error rate < 1% AND dropped = 0 AND p95 < 2 x mock latency", groups=summary), fh, indent=2)
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])

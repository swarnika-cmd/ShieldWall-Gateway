"""Summarise a py-spy `--format raw` (collapsed stacks) file into markdown tables.

    python bench/analyze_stacks.py stacks.txt [--top 15] [--title "..."]

Input lines look like `process ...;thread (id): name;frame (file:line);frame ... <samples>`.
Threads are split into the event-loop thread (MainThread) and the asyncio.to_thread pool
(threads named uvloop_N: uvloop names its default executor that way).

Metrics, per thread group:
  inclusive % = samples whose stack contains the frame at least once / samples of the group
  self %      = samples whose LEAF frame is that frame / samples of the group
Inclusive keys drop line numbers (function + file); self keys keep them.

Bucket table: each sample goes to the FIRST bucket (in BUCKETS order) whose predicate matches
anywhere in its stack, so percentages add up to 100 per group. The order matters: Celery
publishing (which ends in a synchronous Redis call) is claimed before Redis, and so on.
A sample that matches both the import-probe and the pool-scan predicate (the probe runs inside
_assign_requests_to_connections) is credited to the import probe, which comes first.
"event loop idle" is a sample whose leaf is the asyncio runner (the loop waiting in its selector).
With --idle recordings the pool-idle bucket is the time pool threads sit waiting for work.
"""
import argparse
import gzip
import re
from collections import Counter
from typing import Callable, Dict, List, Tuple

Stack = Tuple[str, ...]


def has(*needles: str) -> Callable[[Stack], bool]:
    return lambda frames: any(n in f for f in frames for n in needles)


def leaf_is(*needles: str) -> Callable[[Stack], bool]:
    return lambda frames: any(n in frames[-1] for n in needles)


# The httpcore sub-buckets exist because a first pass showed most event-loop time inside httpcore.
# (bucket, predicate over the frames of one stack; first match wins)
BUCKETS: List[Tuple[str, Callable[[Stack], bool]]] = [
    ("pool thread idle (waiting for work)", leaf_is("_worker (concurrent/futures/thread.py")),
    ("Celery task publish (celery/kombu, sync Redis LPUSH)", has("celery/", "kombu/", "enqueue_log (main.py")),
    ("tiktoken counting", has("tiktoken/", "count_text_tokens", "estimate_input_tokens")),
    ("regex PII scans (pii.py)", has("pii.py")),
    ("Redis round trips, budget (redis.asyncio)", has("redis/", "budget.py")),
    ("DB (psycopg/db.py/auth.py)", has("psycopg", "/db.py", "auth.py")),
    ("JSON (de)serialisation", has("json/", "orjson", "_content.py", "model_dump", "pydantic")),
    ("httpcore: per-call import probe (current_async_library -> importlib)", has("current_async_library (httpcore")),
    ("httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable)",
     has("_assign_requests_to_connections", "is_socket_readable", "is_idle (httpcore", "is_queued (httpcore")),
    ("httpx/httpcore other (request build, send, response read)", has("httpx/", "httpcore/")),
    ("asyncio.to_thread dispatch/wait", has("to_thread (asyncio/threads.py", "run_in_executor")),
    ("logging", has("logging/")),
    ("event loop idle (stack ends at the asyncio runner)", leaf_is("run (asyncio/runners")),
    ("framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools)",
     has("uvicorn/", "starlette/", "fastapi/", "anyio/", "h11", "httptools")),
]
OTHER = "other (no frame matched)"
PLUMBING = re.compile(
    r"^(<module>|_bootstrap|_bootstrap_inner|run \(threading|_worker \(concurrent|run \(concurrent|main \(click|invoke \(click|__call__ \(click"
    r"|run \(asyncio/runners|asyncio_run|run \(uvicorn|main \(uvicorn|run_asgi|__call__ \(uvicorn|__call__ \(fastapi|__call__ \(starlette"
    r"|wrapped_app|app \(fastapi|handle \((fastapi|starlette)|app \(starlette)")


def parse(path: str):
    rows = []
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            stack, _, count = line.rpartition(" ")
            if not count.isdigit():   # py-spy sometimes appends a warning line to the raw output
                continue
            parts = stack.split(";")
            frames = tuple(parts[2:]) or ("(no python frames)",)
            thread = parts[1] if len(parts) > 1 else "?"
            group = "event loop (MainThread)" if "MainThread" in thread else (
                "to_thread pool (uvloop_N)" if "uvloop_" in thread else f"other ({thread})")
            rows.append((group, thread, frames, int(count)))
    return rows


def strip_line(frame: str) -> str:
    return re.sub(r":\d+\)$", ")", frame)


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def analyse(rows, top: int, title: str) -> str:
    groups: Dict[str, list] = {}
    for r in rows:
        groups.setdefault(r[0], []).append(r)
    total = sum(r[3] for r in rows)
    out = [f"# {title}", ""]
    out.append(f"Total samples: {total}. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.")
    out.append("")
    out.append("| Group | Threads seen | Samples | Share of all samples |")
    out.append("|---|---:|---:|---:|")
    for g, rs in sorted(groups.items(), key=lambda kv: -sum(r[3] for r in kv[1])):
        n = sum(r[3] for r in rs)
        out.append(f"| {g} | {len({r[1] for r in rs})} | {n} | {pct(n, total)} |")

    for g, rs in sorted(groups.items(), key=lambda kv: -sum(r[3] for r in kv[1])):
        n = sum(r[3] for r in rs)
        out += ["", f"## {g}", ""]
        buckets: Counter = Counter()
        for _, _, frames, c in rs:
            for name, pred in BUCKETS:
                if pred(frames):
                    buckets[name] += c
                    break
            else:
                buckets[OTHER] += c
        out += ["Buckets (first match wins, adds to 100%):", "",
                "| Bucket | Samples | % of group |", "|---|---:|---:|"]
        for name, c in buckets.most_common():
            out.append(f"| {name} | {c} | {pct(c, n)} |")
        active = n - buckets.get("pool thread idle (waiting for work)", 0)
        if active != n:
            out.append("")
            out.append(f"Excluding pool-idle samples, the remaining {active} samples are the busy view:")
            out += ["", "| Bucket | % of busy samples |", "|---|---:|"]
            for name, c in buckets.most_common():
                if not name.startswith("pool thread idle"):
                    out.append(f"| {name} | {pct(c, active)} |")

        incl: Counter = Counter()
        self_: Counter = Counter()
        for _, _, frames, c in rs:
            for f in {strip_line(x) for x in frames}:
                incl[f] += c
            self_[frames[-1]] += c
        out += ["", f"Top {top} frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):", "",
                "| Frame | Inclusive | % of group |", "|---|---:|---:|"]
        shown = 0
        for f, c in incl.most_common():
            if PLUMBING.search(f):
                continue
            out.append(f"| `{f}` | {c} | {pct(c, n)} |")
            shown += 1
            if shown == top:
                break
        out += ["", f"Top {top} frames by self % (leaf frame):", "",
                "| Frame | Self | % of group |", "|---|---:|---:|"]
        for f, c in self_.most_common(top):
            out.append(f"| `{f}` | {c} | {pct(c, n)} |")
    out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stacks")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--title", default="py-spy collapsed stacks")
    args = ap.parse_args()
    print(analyse(parse(args.stacks), args.top, args.title))


if __name__ == "__main__":
    main()

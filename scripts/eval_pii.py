"""Measure pii.py's per-entity precision and recall on tests/data/pii_labelled.jsonl.

    python scripts/eval_pii.py                  # writes bench/results/pii-eval.json and .md

How detections are obtained: the rules in pii.PII_RULES are applied in order, exactly as
PiiMasker.mask() applies them (each rule runs on the text left by the previous one, so an
email's digits are already gone when the numeric rules run). Because masking shifts offsets,
each match is mapped back to character offsets in the ORIGINAL text. The script asserts, for
every sample, that this replay produces the same masked text as PiiMasker().mask(); if the
detector changes in a way the replay does not follow, the run fails instead of reporting
numbers for a different detector.

Match rule: a predicted span and a labelled span match when they have the SAME TYPE and
OVERLAP by at least one character. Each labelled span matches at most one prediction and
vice versa (greedy, largest overlap first).
  TP = matched pairs            FP = predictions with no match     FN = labelled spans with no match
  precision = TP / (TP + FP)    recall = TP / (TP + FN)            F1 = 2PR / (P + R)
Exact-span agreement (same type, same start and end) is reported as a side figure.
Types the detector emits that the dataset does not label (for example SSN) appear as rows with
zero labelled spans; any detection of them is a false positive.
"""
import argparse
import datetime as dt
import json
import os
import platform
import re
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pii import PII_RULES, PiiMasker  # noqa: E402

DATASET = os.path.join(ROOT, "tests", "data", "pii_labelled.jsonl")
OUT_DIR = os.path.join(ROOT, "bench", "results")

Span = Tuple[str, int, int]  # type, start, end


def detect(text: str) -> Tuple[List[Span], str]:
    """Replay PiiMasker.mask() and return (spans in original coordinates, masked text)."""
    masker = PiiMasker()
    cur = text
    # origin[i] = (start, end) in the original text of the character cur[i]
    origin: List[Tuple[int, int]] = [(i, i + 1) for i in range(len(text))]
    spans: List[Span] = []
    for entity, pattern, validator in PII_RULES:
        pieces: List[str] = []
        new_origin: List[Tuple[int, int]] = []
        last = 0
        for m in pattern.finditer(cur):
            value = m.group(0)
            if validator and not validator(value):
                continue
            o_start, o_end = origin[m.start()][0], origin[m.end() - 1][1]
            spans.append((entity, o_start, o_end))
            placeholder = masker._placeholder(entity, value)
            pieces.append(cur[last:m.start()])
            new_origin.extend(origin[last:m.start()])
            pieces.append(placeholder)
            new_origin.extend([(o_start, o_end)] * len(placeholder))
            last = m.end()
        pieces.append(cur[last:])
        new_origin.extend(origin[last:])
        cur, origin = "".join(pieces), new_origin
    expected = PiiMasker().mask(text)
    if cur != expected:
        raise AssertionError(f"span replay diverged from PiiMasker.mask():\n{cur!r}\n{expected!r}")
    return spans, cur


def overlap(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def match(gold: List[Span], pred: List[Span]) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """Greedy one-to-one matching of same-type overlapping spans. Returns (pairs, unmatched_gold, unmatched_pred)."""
    candidates = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(pred):
            if g[0] == p[0]:
                ov = overlap(g[1:], p[1:])
                if ov > 0:
                    candidates.append((ov, gi, pi))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_g, used_p, pairs = set(), set(), []
    for _, gi, pi in candidates:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        pairs.append((gi, pi))
    return (pairs,
            [i for i in range(len(gold)) if i not in used_g],
            [i for i in range(len(pred)) if i not in used_p])


def prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": p, "recall": r, "f1": f}


def evaluate(rows: List[dict]) -> dict:
    counts = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "exact": 0, "gold": 0})
    by_category = defaultdict(lambda: {"rows": 0, "fp": 0, "fn": 0})
    errors = {"fp": [], "fn": []}
    for row in rows:
        gold = [(e["type"], e["start"], e["end"]) for e in row["entities"]]
        pred, _ = detect(row["text"])
        pairs, miss_g, extra_p = match(gold, pred)
        for gi, pi in pairs:
            counts[gold[gi][0]]["tp"] += 1
            if gold[gi][1:] == pred[pi][1:]:
                counts[gold[gi][0]]["exact"] += 1
        for g in gold:
            counts[g[0]]["gold"] += 1
        for gi in miss_g:
            counts[gold[gi][0]]["fn"] += 1
            by_category[row["category"]]["fn"] += 1
            errors["fn"].append({"id": row["id"], "type": gold[gi][0], "value": row["text"][gold[gi][1]:gold[gi][2]],
                                 "category": row["category"]})
        for pi in extra_p:
            counts[pred[pi][0]]["fp"] += 1
            by_category[row["category"]]["fp"] += 1
            errors["fp"].append({"id": row["id"], "type": pred[pi][0], "value": row["text"][pred[pi][1]:pred[pi][2]],
                                 "category": row["category"]})
        by_category[row["category"]]["rows"] += 1

    per_type = {}
    for etype in sorted(counts):
        c = counts[etype]
        per_type[etype] = {**c, **prf(c["tp"], c["fp"], c["fn"])}
    tp = sum(c["tp"] for c in counts.values())
    fp = sum(c["fp"] for c in counts.values())
    fn = sum(c["fn"] for c in counts.values())
    micro = {"tp": tp, "fp": fp, "fn": fn, **prf(tp, fp, fn)}
    return {"per_type": per_type, "micro": micro, "by_category": dict(by_category), "errors": errors}


def fmt(v) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def render_md(result: dict, meta: dict) -> str:
    lines = [
        "# PII detector evaluation",
        "",
        f"Date (UTC): {meta['date']}  ",
        f"Dataset: `{meta['dataset']}` ({meta['rows']} rows, {meta['labelled_spans']} labelled spans), "
        f"built by `scripts/make_pii_dataset.py` with seed {meta['seed']}  ",
        f"Detector: `pii.PII_RULES` (working tree); Python {meta['python']}",
        "",
        "Match rule: same entity type and at least one overlapping character; one-to-one matching. "
        "TP = matched, FP = unmatched prediction, FN = unmatched labelled span.",
        "",
        "| Type | Labelled | TP | FP | FN | Precision | Recall | F1 | Exact-span TP |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for etype, c in result["per_type"].items():
        lines.append(f"| {etype} | {c['gold']} | {c['tp']} | {c['fp']} | {c['fn']} | {fmt(c['precision'])} "
                     f"| {fmt(c['recall'])} | {fmt(c['f1'])} | {c['exact']} |")
    m = result["micro"]
    lines.append(f"| **all (micro)** | {m['tp'] + m['fn']} | {m['tp']} | {m['fp']} | {m['fn']} "
                 f"| {fmt(m['precision'])} | {fmt(m['recall'])} | {fmt(m['f1'])} | |")
    lines += ["", "## Errors by dataset category", "",
              "| Category | Rows | FP | FN |", "|---|---:|---:|---:|"]
    for cat, c in sorted(result["by_category"].items()):
        lines.append(f"| {cat} | {c['rows']} | {c['fp']} | {c['fn']} |")
    for kind, title in (("fp", "False positives"), ("fn", "False negatives")):
        errs = result["errors"][kind]
        lines += ["", f"## {title} ({len(errs)})", ""]
        if not errs:
            lines.append("None.")
        for e in errs[:40]:
            lines.append(f"- `{e['id']}` ({e['category']}) {e['type']}: `{e['value']}`")
        if len(errs) > 40:
            lines.append(f"- ... {len(errs) - 40} more in pii-eval.json")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args()

    with open(args.dataset, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from make_pii_dataset import SEED  # same seed the file was built with

    result = evaluate(rows)
    meta = {
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": os.path.relpath(args.dataset, ROOT),
        "seed": SEED,
        "rows": len(rows),
        "labelled_spans": sum(len(r["entities"]) for r in rows),
        "python": platform.python_version(),
        "match_rule": "same type and overlapping span (>=1 char), one-to-one",
    }
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "pii-eval.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, **result}, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(args.out_dir, "pii-eval.md"), "w", encoding="utf-8") as fh:
        fh.write(render_md(result, meta))
    print(render_md(result, meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())

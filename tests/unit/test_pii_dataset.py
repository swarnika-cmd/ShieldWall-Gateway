"""The labelled PII dataset must be trustworthy before precision/recall numbers mean anything.

Checksums here come from scripts/make_pii_dataset.py (written independently of pii.py) and
are also cross-checked against pii.py's implementations on every labelled value.
"""
import json
import os
import re

import pytest

import pii
from scripts import make_pii_dataset as ds

DATASET = os.path.join(os.path.dirname(__file__), "..", "data", "pii_labelled.jsonl")
TYPES = {"EMAIL", "IN_MOBILE", "PAN", "AADHAAR", "CREDIT_CARD"}


@pytest.fixture(scope="module")
def rows():
    with open(DATASET, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def test_independent_checksums_match_known_vectors():
    for number in ["4111111111111111", "5500005555555559", "378282246310005", "79927398713"]:
        assert ds.luhn_ok(number)
    for number in ["4111111111111112", "79927398710"]:
        assert not ds.luhn_ok(number)
    for prefix, check in [("236", "3"), ("12345", "1"), ("142857", "0")]:
        assert ds.verhoeff_complete(prefix) == prefix + check
        assert ds.verhoeff_ok(prefix + check)


def test_independent_checksums_agree_with_pii_module():
    import random

    rng = random.Random(7)
    for _ in range(2000):
        n = ds.digits(rng, rng.choice([12, 13, 15, 16]))
        assert ds.luhn_ok(n) == pii.luhn_valid(n)
        assert ds.verhoeff_ok(n) == pii.verhoeff_valid(n)


def test_schema_and_spans(rows):
    assert len(rows) >= 1000
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        assert set(r) == {"id", "category", "text", "entities"}
        spans = sorted((e["start"], e["end"]) for e in r["entities"])
        for e in r["entities"]:
            assert e["type"] in TYPES
            assert r["text"][e["start"]:e["end"]] == e["value"]
        for (_, end), (start, _) in zip(spans, spans[1:]):
            assert end <= start, f"overlapping labels in {r['id']}"
    assert {e["type"] for r in rows for e in r["entities"]} == TYPES


def test_labelled_aadhaar_numbers_have_valid_verhoeff(rows):
    values = [e["value"] for r in rows for e in r["entities"] if e["type"] == "AADHAAR"]
    assert len(values) >= 100
    for v in values:
        digits = only_digits(v)
        assert len(digits) == 12 and digits[0] in "23456789", v
        assert ds.verhoeff_ok(digits), v
        assert pii.verhoeff_valid(digits), v


def test_labelled_cards_have_valid_luhn(rows):
    values = [e["value"] for r in rows for e in r["entities"] if e["type"] == "CREDIT_CARD"]
    assert len(values) >= 100
    for v in values:
        digits = only_digits(v)
        assert 13 <= len(digits) <= 19, v
        assert ds.luhn_ok(digits), v
        assert pii.luhn_valid(digits), v


def test_labelled_pan_and_mobile_structure(rows):
    for r in rows:
        for e in r["entities"]:
            if e["type"] == "PAN":
                assert re.fullmatch(r"[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]", e["value"]), e["value"]
            if e["type"] == "IN_MOBILE":
                digits = only_digits(e["value"])
                assert digits[-10:][0] in "6789" and len(digits[-10:]) == 10, e["value"]
                assert digits[:-10] in ("", "91", "0"), e["value"]
            if e["type"] == "EMAIL":
                assert re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", e["value"]), e["value"]


def test_negatives_have_no_labels_and_fail_their_checksums(rows):
    negatives = [r for r in rows if r["category"].startswith("neg_")]
    assert len(negatives) >= 350
    assert all(r["entities"] == [] for r in negatives)

    non_luhn = [r for r in negatives if r["category"] == "neg_card_like_non_luhn"]
    assert len(non_luhn) >= 40
    for r in non_luhn:
        runs = re.findall(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])", r["text"])
        assert runs, r["text"]
        for run in runs:
            assert not ds.luhn_ok(only_digits(run)), r["text"]

    non_verhoeff = [r for r in negatives if r["category"] == "neg_aadhaar_like_non_verhoeff"]
    assert len(non_verhoeff) >= 40
    for r in non_verhoeff:
        runs = re.findall(r"(?<![\w-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\w-])", r["text"])
        assert runs, r["text"]
        for run in runs:
            assert not ds.verhoeff_ok(only_digits(run)), r["text"]


def test_dataset_is_reproducible_from_the_seed(rows):
    pytest.importorskip("faker")
    rebuilt = ds.dumps(ds.generate(ds.SEED))
    with open(DATASET, encoding="utf-8") as fh:
        assert fh.read() == rebuilt

"""Documents what pii.py does NOT detect today, so the README's claims about gaps stay checkable.

Each test asserts the CURRENT behaviour. If detection is improved, the test fails and should be
turned into a normal positive case in test_pii.py.
"""
from pii import PiiMasker, verhoeff_check_digit


def mask(text: str) -> str:
    return PiiMasker().mask(text)


def aadhaar(first11: str = "23412341234") -> str:
    return first11 + verhoeff_check_digit(first11)


def test_gap_mobile_with_hyphens_in_other_places_is_not_detected():
    assert mask("call 98-7654-3210") == "call 98-7654-3210"
    assert mask("call 9876-543210") == "call 9876-543210"


def test_gap_lowercase_pan_is_not_detected():
    assert mask("PAN abcde1234f") == "PAN abcde1234f"


def test_gap_aadhaar_with_mixed_separators_is_not_detected():
    n = aadhaar()
    text = f"aadhaar {n[:4]} {n[4:8]}-{n[8:]}"
    assert mask(text) == text


def test_checksum_valid_twelve_digit_reference_is_masked_as_aadhaar():
    # About 1 in 10 random 12-digit references (first digit 2-9) pass Verhoeff by chance.
    assert mask(f"ref {aadhaar()}") == "ref [REDACTED_AADHAAR_1]"

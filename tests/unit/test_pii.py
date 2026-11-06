import pytest

from pii import PiiMasker, unmask_text, verhoeff_check_digit


def aadhaar(first11: str) -> str:
    return first11 + verhoeff_check_digit(first11)


VALID_AADHAAR = aadhaar("23412341234")
INVALID_AADHAAR = VALID_AADHAAR[:-1] + str((int(VALID_AADHAAR[-1]) + 1) % 10)


def mask(text: str) -> str:
    return PiiMasker().mask(text)


@pytest.mark.parametrize("text, entity", [
    ("mail me at riya.sharma+work@example.co.in", "EMAIL"),
    ("card 4111 1111 1111 1111 please", "CREDIT_CARD"),
    ("card 4111-1111-1111-1111", "CREDIT_CARD"),
    ("card 4111111111111111", "CREDIT_CARD"),
    ("amex 378282246310005", "CREDIT_CARD"),
    (f"aadhaar {VALID_AADHAAR}", "AADHAAR"),
    (f"aadhaar {VALID_AADHAAR[:4]} {VALID_AADHAAR[4:8]} {VALID_AADHAAR[8:]}", "AADHAAR"),
    ("PAN is ABCPE1234F", "PAN"),
    ("call +91 98765 43210", "IN_MOBILE"),
    ("call +919876543210", "IN_MOBILE"),
    ("call 09876543210", "IN_MOBILE"),
    ("call 9876543210.", "IN_MOBILE"),
    ("ssn 123-45-6789", "SSN"),
    ("key sk-proj-abcdefghijklmnopqrstuvwxyz0123456789", "OPENAI_KEY"),
    ("aws AKIAABCDEFGHIJKLMNOP", "AWS_KEY"),
])
def test_detects_pii(text, entity):
    masked = mask(text)
    assert f"[REDACTED_{entity}_1]" in masked, masked


@pytest.mark.parametrize("text", [
    "order id 4111111111111112 shipped",          # 16 digits, fails Luhn
    "ref 1234567812345678",                        # 16 digits, fails Luhn
    "event at 1762502400123 ms",                   # millisecond timestamp (starts with 1)
    "unix time 1762502400",                        # 10-digit timestamp, starts with 1
    "Flipkart order OD428273641928374610",         # letters glued to digits
    f"aadhaar-like {INVALID_AADHAAR}",             # 12 digits, fails Verhoeff
    "invoice 2023-11-15 total 4500",               # dates and amounts
    "phone 5876543210",                            # Indian mobiles start with 6-9
    "pan-like ABCDE12345",                         # wrong PAN shape
    "pan-like ABCXE1234F",                         # 4th letter X is not a holder type
    "version 10.2.3.4 build 20231115",
])
def test_ignores_hard_negatives(text):
    assert mask(text) == text


def test_aadhaar_not_matched_inside_longer_spaced_number():
    # 16-digit non-card number: the first 12 digits must not be treated as Aadhaar.
    text = f"{VALID_AADHAAR[:4]} {VALID_AADHAAR[4:8]} {VALID_AADHAAR[8:]} 9999"
    assert "AADHAAR" not in mask(text)


def test_placeholders_are_unique_across_messages():
    """Regression for the v1 bug: counters were reset per message."""
    masker = PiiMasker()
    messages = [
        {"role": "user", "content": "first: alice@example.com"},
        {"role": "user", "content": "second: bob@example.com"},
    ]
    masked = masker.mask_messages(messages)
    assert masked[0]["content"] == "first: [REDACTED_EMAIL_1]"
    assert masked[1]["content"] == "second: [REDACTED_EMAIL_2]"
    reply = "[REDACTED_EMAIL_1] wrote to [REDACTED_EMAIL_2]"
    assert masker.unmask(reply) == "alice@example.com wrote to bob@example.com"
    assert masker.entity_counts() == {"EMAIL": 2}


def test_same_value_reuses_placeholder():
    masker = PiiMasker()
    out = masker.mask_messages([
        {"role": "user", "content": "a@b.io"},
        {"role": "assistant", "content": "noted a@b.io"},
    ])
    assert out[1]["content"] == "noted [REDACTED_EMAIL_1]"
    assert len(masker.mappings) == 1


def test_masks_content_part_lists_and_leaves_images_alone():
    masker = PiiMasker()
    image = {"type": "image_url", "image_url": {"url": "https://x/y.png"}}
    out = masker.mask_messages([{"role": "user", "content": [
        {"type": "text", "text": "mail x@y.com"}, image]}])
    assert out[0]["content"][0]["text"] == "mail [REDACTED_EMAIL_1]"
    assert out[0]["content"][1] == image


def test_masking_does_not_mutate_input():
    messages = [{"role": "user", "content": "x@y.com"}]
    PiiMasker().mask_messages(messages)
    assert messages[0]["content"] == "x@y.com"


def test_unmask_is_single_pass():
    # An original value that looks like a placeholder is not expanded again.
    mappings = {"[REDACTED_EMAIL_1]": "[REDACTED_EMAIL_2]", "[REDACTED_EMAIL_2]": "b@c.d"}
    assert unmask_text("[REDACTED_EMAIL_1]", mappings) == "[REDACTED_EMAIL_2]"


def test_unknown_placeholder_left_as_is():
    assert unmask_text("[REDACTED_EMAIL_9]", {"[REDACTED_EMAIL_1]": "a@b.c"}) == "[REDACTED_EMAIL_9]"


def test_mixed_message():
    masker = PiiMasker()
    text = ("Riya (riya@example.com, +91 98765 43210) paid with 4111 1111 1111 1111; "
            f"PAN ABCPE1234F, Aadhaar {VALID_AADHAAR}. Order 1762502400123.")
    masked = masker.mask(text)
    for raw in ["riya@example.com", "98765 43210", "4111 1111 1111 1111", "ABCPE1234F", VALID_AADHAAR]:
        assert raw not in masked
    assert "1762502400123" in masked
    assert masker.unmask(masked) == text
    assert masker.entity_counts() == {"EMAIL": 1, "IN_MOBILE": 1, "CREDIT_CARD": 1, "PAN": 1, "AADHAAR": 1}

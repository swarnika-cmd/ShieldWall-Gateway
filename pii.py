"""Regex-based PII and secret masking.

How it works:
  * Each rule is a regex. Some rules also run a checksum (Luhn for card
    numbers, Verhoeff for Aadhaar) so random digit runs are not masked.
  * A PiiMasker object lives for ONE request. It is shared by every message
    in that request, so two different emails in two different messages get
    two different placeholders ([REDACTED_EMAIL_1], [REDACTED_EMAIL_2]).
  * The token -> original mapping only lives in memory for the duration of
    the request. It is never written to Redis, Postgres or logs.

Known limits (regex only): names, postal addresses and free-form personal
details are NOT detected, and unusual formats will be missed.
"""
import re
from collections import Counter
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Checksums
# ---------------------------------------------------------------------------


def luhn_valid(number: str) -> bool:
    """Luhn (mod 10) check used by payment card numbers."""
    if not number.isdigit():
        return False
    total = 0
    # Walk from the rightmost digit; double every second digit.
    for i, ch in enumerate(reversed(number)):
        digit = int(ch)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


# Verhoeff tables (dihedral group D5). Aadhaar's last digit is a Verhoeff
# check digit over the first 11 digits.
_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(number: str) -> bool:
    """True if the last digit is a correct Verhoeff check digit."""
    if not number.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(number: str) -> str:
    """Digit to append to `number` so that the result is Verhoeff-valid."""
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return str(_VERHOEFF_INV[c])


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _is_card(match: str) -> bool:
    digits = _digits(match)
    # Card networks start with 2-6 (Mastercard, Amex/Diners/JCB, Visa,
    # Mastercard, Discover/RuPay) or 8 (RuPay). This, plus Luhn, rejects most
    # order ids and millisecond timestamps (which start with 1).
    return 13 <= len(digits) <= 19 and digits[0] in "234568" and luhn_valid(digits)


def _is_aadhaar(match: str) -> bool:
    return verhoeff_valid(_digits(match))


# (name, regex, optional validator). Order matters: secrets and emails run
# first so their digits are already replaced before the numeric rules run.
Rule = Tuple[str, "re.Pattern[str]", Optional[Callable[[str], bool]]]

PII_RULES: List[Rule] = [
    ("OPENAI_KEY", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}"), None),
    ("AWS_KEY", re.compile(r"\bAKIA[A-Z0-9]{16}\b"), None),
    (
        "AWS_SECRET_KEY",
        re.compile(r"\bAWS_SECRET_ACCESS_KEY\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?", re.IGNORECASE),
        None,
    ),
    ("ENV_VAR", re.compile(r"\b[A-Z_][A-Z0-9_]*\s*=\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"), None),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), None),
    # 13-19 digits, optionally separated by single spaces or dashes.
    ("CREDIT_CARD", re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])"), _is_card),
    # 12 digits, first digit 2-9, optionally grouped 4-4-4 with the SAME
    # separator (space or dash) in both places.
    # The extra look-arounds stop it from matching 12 digits inside a longer
    # spaced number such as "4111 1111 1111 1111".
    (
        "AADHAAR",
        re.compile(r"(?<![\d-])(?<!\d )[2-9]\d{3}([ -]?)\d{4}\1\d{4}(?![\d-])(?! \d)"),
        _is_aadhaar,
    ),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), None),
    # PAN: 5 letters, 4 digits, 1 letter. The 4th letter is the holder type
    # (P = person, C = company, H, F, A, T, B, L, J, G).
    ("PAN", re.compile(r"\b[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]\b"), None),
    # Indian mobile: optional +91 / 91 / 0 prefix, then 10 digits starting 6-9.
    (
        "IN_MOBILE",
        re.compile(r"(?<![\w+])(?:\+91[ -]?|91[ -]|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)"),
        None,
    ),
]

PLACEHOLDER_RE = re.compile(r"\[REDACTED_[A-Z_]+_\d+\]")


class PiiMasker:
    """Masks PII for one request and can reverse the masking afterwards."""

    def __init__(self) -> None:
        self.mappings: Dict[str, str] = {}   # placeholder -> original value
        self._placeholder_for: Dict[str, str] = {}  # original value -> placeholder
        self._counters: Counter = Counter()  # entity type -> last number used

    def _placeholder(self, entity: str, value: str) -> str:
        # The same value always gets the same placeholder within a request.
        existing = self._placeholder_for.get(value)
        if existing:
            return existing
        self._counters[entity] += 1
        token = f"[REDACTED_{entity}_{self._counters[entity]}]"
        self.mappings[token] = value
        self._placeholder_for[value] = token
        return token

    def mask(self, text: str) -> str:
        if not text:
            return text
        for entity, pattern, validator in PII_RULES:
            def replace(match: "re.Match[str]", entity=entity, validator=validator) -> str:
                value = match.group(0)
                if validator and not validator(value):
                    return value
                return self._placeholder(entity, value)

            text = pattern.sub(replace, text)
        return text

    def unmask(self, text: str) -> str:
        return unmask_text(text, self.mappings)

    def entity_counts(self) -> Dict[str, int]:
        """Number of distinct values masked per entity type. Safe to log."""
        return dict(self._counters)

    def mask_messages(self, messages: List[dict]) -> List[dict]:
        """Mask the text of every chat message (string or content-part list)."""
        masked = []
        for message in messages:
            new_message = dict(message)
            content = new_message.get("content")
            if isinstance(content, str):
                new_message["content"] = self.mask(content)
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        part = {**part, "text": self.mask(part.get("text", ""))}
                    parts.append(part)
                new_message["content"] = parts
            masked.append(new_message)
        return masked


def unmask_text(text: str, mappings: Dict[str, str]) -> str:
    """Replace placeholders with original values in ONE pass.

    A single regex pass means an original value that happens to look like
    a placeholder is never replaced a second time.
    """
    if not text or not mappings:
        return text
    return PLACEHOLDER_RE.sub(lambda m: mappings.get(m.group(0), m.group(0)), text)

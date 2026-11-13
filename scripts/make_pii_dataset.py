"""Generate the labelled PII dataset used to measure pii.py's precision and recall.

    python scripts/make_pii_dataset.py            # writes tests/data/pii_labelled.jsonl

Deterministic: the same SEED and the same Faker version always give the same file
(tests/unit/test_pii_dataset.py regenerates it and compares). Faker (locale en_IN) supplies
names, cities, companies and some email addresses; everything else comes from a seeded
random.Random.

Each row:
    {"id", "category", "text", "entities": [{"type", "start", "end", "value"}]}
`start`/`end` are character offsets into `text` (end exclusive). Entity types use the names
in pii.py (EMAIL, IN_MOBILE, PAN, AADHAAR, CREDIT_CARD). Hard negatives have no entities.

The checksum helpers below are written independently of pii.py on purpose, so the labels do
not depend on the code being evaluated.
"""
import json
import os
import random
import re
import sys
from typing import Dict, List, Tuple

SEED = 20261113
OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "tests", "data", "pii_labelled.jsonl")

# --------------------------------------------------------------------------------------
# Checksums (independent implementations)
# --------------------------------------------------------------------------------------


def luhn_ok(number: str) -> bool:
    """Luhn: from the right, double every second digit, subtract 9 if above 9, sum % 10 == 0."""
    if not number.isdigit():
        return False
    total = 0
    for idx, ch in enumerate(reversed(number)):
        d = int(ch)
        if idx % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def luhn_complete(body: str) -> str:
    """`body` plus the check digit that makes it Luhn-valid."""
    for check in "0123456789":
        if luhn_ok(body + check):
            return body + check
    raise AssertionError("unreachable")


def _verhoeff_tables() -> Tuple[List[List[int]], List[List[int]]]:
    # Multiplication table of the dihedral group D5, built from its definition.
    d = [[0] * 10 for _ in range(10)]
    for i in range(10):
        for j in range(10):
            if i < 5 and j < 5:
                d[i][j] = (i + j) % 5
            elif i < 5 <= j:
                d[i][j] = (i + (j - 5)) % 5 + 5
            elif i >= 5 > j:
                d[i][j] = ((i - 5) - j) % 5 + 5
            else:
                d[i][j] = ((i - 5) - (j - 5)) % 5
    # Position permutation: the base permutation applied i times.
    base = [1, 5, 7, 6, 2, 8, 3, 0, 9, 4]
    p = [list(range(10))]
    for _ in range(7):
        prev = p[-1]
        p.append([prev[base[x]] for x in range(10)])
    return d, p


_D, _P = _verhoeff_tables()


def verhoeff_ok(number: str) -> bool:
    if not number.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_complete(body: str) -> str:
    for check in "0123456789":
        if verhoeff_ok(body + check):
            return body + check
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------------------
# Value generators
# --------------------------------------------------------------------------------------


def digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def gen_mobile(rng: random.Random) -> str:
    """A 10-digit Indian mobile: first digit 6-9."""
    return rng.choice("6789") + digits(rng, 9)


MOBILE_FORMATS = [
    "+91 {a} {b}", "+91 {a} {b}", "+91-{a}{b}", "+91{a}{b}", "+91 {a}{b}",
    "{a}{b}", "{a}{b}", "{a} {b}", "{a}-{b}", "0{a}{b}", "91 {a}{b}", "91-{a}{b}",
]


def fmt_mobile(rng: random.Random) -> str:
    num = gen_mobile(rng)
    return rng.choice(MOBILE_FORMATS).format(a=num[:5], b=num[5:])


def gen_pan(rng: random.Random) -> str:
    """5 letters + 4 digits + 1 letter; 4th letter is the holder type, 5th the surname initial."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    holder = rng.choices("PCHFATBLJG", weights=[70, 10, 4, 4, 3, 3, 2, 2, 1, 1])[0]
    return (rng.choice(letters) + rng.choice(letters) + rng.choice(letters) + holder
            + rng.choice(letters) + digits(rng, 4) + rng.choice(letters))


def gen_aadhaar(rng: random.Random) -> str:
    """12 digits, first digit 2-9, last digit a valid Verhoeff check digit."""
    return verhoeff_complete(rng.choice("23456789") + digits(rng, 10))


def fmt_aadhaar(rng: random.Random) -> str:
    num = gen_aadhaar(rng)
    sep = rng.choices(["", " ", "-"], weights=[35, 55, 10])[0]
    return sep.join([num[:4], num[4:8], num[8:]])


# brand -> (IIN prefixes, lengths)
CARD_BRANDS: Dict[str, Tuple[List[str], List[int]]] = {
    "visa": (["4"], [16, 16, 16, 13]),
    "mastercard": (["51", "52", "53", "54", "55", "2221", "2500", "2720"], [16]),
    "amex": (["34", "37"], [15]),
    "diners": (["36", "300", "305"], [14]),
    "discover": (["6011", "65", "644"], [16]),
    "rupay": (["60", "6521", "508", "817", "818"], [16]),
    "jcb": (["3528", "3589"], [16]),
}


def fmt_card(rng: random.Random) -> str:
    brand = rng.choice(list(CARD_BRANDS))
    prefixes, lengths = CARD_BRANDS[brand]
    prefix, length = rng.choice(prefixes), rng.choice(lengths)
    num = luhn_complete(prefix + digits(rng, length - len(prefix) - 1))
    assert len(num) == length and luhn_ok(num)
    if length == 15:
        groups = [num[:4], num[4:10], num[10:]]
    elif length == 14:
        groups = [num[:4], num[4:10], num[10:]]
    elif length == 16:
        groups = [num[i:i + 4] for i in range(0, 16, 4)]
    else:
        groups = [num]
    sep = rng.choices(["", " ", "-"], weights=[30, 55, 15])[0]
    return sep.join(groups)


def gen_non_luhn(rng: random.Random, length: int, first: str = "") -> str:
    while True:
        num = (first or rng.choice("23456")) + digits(rng, length - 1)
        if not luhn_ok(num):
            return num


def gen_non_verhoeff12(rng: random.Random) -> str:
    while True:
        num = rng.choice("23456789") + digits(rng, 11)
        if not verhoeff_ok(num):
            return num


# --------------------------------------------------------------------------------------
# Templates. {EMAIL} {IN_MOBILE} {PAN} {AADHAAR} {CREDIT_CARD} are labelled slots; {NEG} is an
# unlabelled hard-negative string; {NAME} {CITY} {COMPANY} are Faker filler (never digits).
# --------------------------------------------------------------------------------------

T_EMAIL = [
    "Hi, I'm {NAME}. You can reach me at {EMAIL} about the refund.",
    "Please send the invoice to {EMAIL} and copy accounts.",
    "My login email is {EMAIL}, but I can't reset my password.",
    "Forward this thread to {EMAIL}.",
    "Contact: {EMAIL}",
    "Can you draft a reply to {EMAIL} thanking them for the demo?",
    "Customer {NAME} ({EMAIL}) reported that the app crashes on login.",
    "email={EMAIL}&source=webform",
    "Summarise the complaint from {EMAIL} in two lines.",
    "From: {NAME} <{EMAIL}>\nSubject: Delivery delay",
    "I signed up with {EMAIL} but never got the confirmation.",
    "Write a polite follow-up to {EMAIL}, they have not replied in a week.",
]
T_MOBILE = [
    "Call me on {IN_MOBILE} after 5 pm.",
    "My number is {IN_MOBILE}, please WhatsApp me the tracking link.",
    "The delivery partner could not reach {IN_MOBILE}. Please retry.",
    "Update the contact number for {NAME} to {IN_MOBILE}.",
    "OTP was sent to {IN_MOBILE} but has not arrived.",
    "Phone: {IN_MOBILE}",
    "Hello, this is {NAME} from {CITY}. Ring {IN_MOBILE} if the address is unclear.",
    "Draft an SMS to {IN_MOBILE} confirming the appointment tomorrow.",
    "Customer mobile {IN_MOBILE} is linked to two accounts. How do I merge them?",
    "mobile={IN_MOBILE}",
    "Alternate contact for the {COMPANY} account: {IN_MOBILE}.",
    "Please block the SIM registered as {IN_MOBILE}.",
]
T_PAN = [
    "My PAN is {PAN}, please update it in the KYC form.",
    "PAN: {PAN}",
    "Verify the PAN {PAN} against the name {NAME}.",
    "The form was rejected because the PAN card number {PAN} did not match.",
    "For TDS purposes, the deductee PAN is {PAN}.",
    "Add {PAN} to the vendor master for {COMPANY}.",
    "I am attaching my PAN ({PAN}) and a cancelled cheque.",
    "pan={PAN}&state=KA",
    "Customer {NAME} gave PAN {PAN} during onboarding at {CITY}.",
]
T_AADHAAR = [
    "My Aadhaar number is {AADHAAR}, link it to my account.",
    "Aadhaar: {AADHAAR}",
    "e-KYC failed for Aadhaar {AADHAAR}. What should I do?",
    "Please mask the Aadhaar {AADHAAR} in the attached scan.",
    "{NAME}'s UID is {AADHAAR}, born in {CITY}.",
    "Link {AADHAAR} with the bank account for DBT.",
    "I entered my Aadhaar ({AADHAAR}) but the OTP never came.",
    "aadhaar_no={AADHAAR}",
    "Verification needed for UIDAI number {AADHAAR}.",
]
T_CARD = [
    "My card number is {CREDIT_CARD}, expiry 08/28.",
    "Charge {CREDIT_CARD} for the annual plan.",
    "Card on file: {CREDIT_CARD}",
    "The payment with card {CREDIT_CARD} was declined. Why?",
    "Refund to {CREDIT_CARD} please, the order was cancelled.",
    "Customer {NAME} pasted their card {CREDIT_CARD} into the chat by mistake.",
    "cc={CREDIT_CARD}&cvv_required=true",
    "Can I use {CREDIT_CARD} for an international transaction?",
    "Update billing for {COMPANY} to the card {CREDIT_CARD}.",
]
T_MULTI = [
    "Name: {NAME}. Email {EMAIL}, phone {IN_MOBILE}.",
    "KYC for {NAME}: PAN {PAN}, Aadhaar {AADHAAR}, mobile {IN_MOBILE}.",
    "Please charge {CREDIT_CARD} and email the receipt to {EMAIL}.",
    "Customer {NAME} from {CITY} wrote from {EMAIL}; call back on {IN_MOBILE}.",
    "Onboarding form: Aadhaar {AADHAAR}, PAN {PAN}, email {EMAIL}.",
    "Verify {PAN} and {AADHAAR} for {NAME}, then SMS {IN_MOBILE}.",
    "Billing contact {EMAIL} / {IN_MOBILE}, card {CREDIT_CARD}.",
    "I'm {NAME}. My mobile is {IN_MOBILE} and my backup email is {EMAIL}.",
    "Refund {CREDIT_CARD} (owner {NAME}); proof of identity: PAN {PAN}.",
    "Ticket from {EMAIL}: card {CREDIT_CARD} was charged twice; mobile {IN_MOBILE}.",
]
MULTI_SLOTS = ["EMAIL", "IN_MOBILE", "PAN", "AADHAAR", "CREDIT_CARD"]

# Hard-negative templates: (category, templates, generator of {NEG})
T_PLAIN = [
    "Can you summarise the main differences between a savings account and a current account?",
    "Write a Python function that removes duplicates from a list while keeping the order.",
    "Explain GST input tax credit in simple terms for a small shop in {CITY}.",
    "What is the best way to prepare for a system design interview?",
    "Translate 'Where is the nearest railway station?' into Hindi and Tamil.",
    "Draft a friendly reminder to {NAME} about the quarterly review meeting.",
    "Give me three names for a bakery in {CITY}.",
    "How do I explain a gap year on my resume?",
    "Suggest a weekend itinerary for {CITY} with a focus on food.",
    "{COMPANY} wants a one-page note on our data retention policy.",
]
T_ORDER = [
    "Where is my order {NEG}? It was supposed to arrive yesterday.",
    "Order ID: {NEG}",
    "Please cancel order #{NEG} placed by {NAME}.",
    "Tracking number {NEG} shows no movement for three days.",
    "Return request for shipment {NEG} from {COMPANY}.",
    "ref={NEG}&status=pending",
]
T_TIMESTAMP = [
    "The error occurred at {NEG} according to the logs.",
    "created_at: {NEG}",
    "Request received {NEG}, response sent shortly after.",
    "Compare the events at {NEG} and the retry that followed.",
    '{{"ts": "{NEG}", "level": "warn"}}',
    "Session started at {NEG} from {CITY}.",
]
T_NON_LUHN = [
    "Reference {NEG} was created by the billing system.",
    "Payment gateway txn id {NEG}, status success.",
    "Bank account number {NEG}, IFSC listed separately.",
    "Shipment AWB {NEG} was handed to the courier.",
    "Serial number: {NEG}",
    "Invoice batch id {NEG} failed to import.",
]
T_NON_VERHOEFF = [
    "UPI reference number {NEG} for the transfer to {COMPANY}.",
    "UTR {NEG} credited on the same day.",
    "Case number {NEG} has been escalated.",
    "Reference no. {NEG}",
    "The 12-digit transaction id {NEG} does not appear in our records.",
    "Application number {NEG} for the passport appointment in {CITY}.",
]
T_INVOICE = [
    "Invoice {NEG} is overdue, please advise.",
    "Please find attached {NEG} for the services rendered.",
    "Credit note against {NEG} was issued to {COMPANY}.",
    "PO number {NEG}",
    "Reconcile {NEG} with the bank statement.",
]
T_PHONE_LIKE = [
    "Our overseas office is at {NEG}.",
    "Customer support: {NEG}",
    "The helpline {NEG} is open 24x7.",
    "Landline of the {CITY} branch: {NEG}",
    "Fax {NEG}",
    "Call the regional team on {NEG}.",
]
T_PAN_LIKE = [
    "Is {NEG} a valid PAN?",
    "The code {NEG} was printed on the label.",
    "Part number {NEG}, quantity 12.",
    "Registration {NEG} was found in the register.",
    "Promo code {NEG} expires tonight.",
    "Employee code: {NEG}",
]
T_EMAIL_LIKE = [
    "The reference {NEG} is missing from the build output.",
    "The string {NEG} loads slowly on mobile, any idea why?",
    "Why does the config still point to {NEG}?",
]
def neg_order(rng, fake):
    kind = rng.randrange(5)
    if kind == 0:
        return f"ORD-{rng.randrange(2024, 2027)}-{digits(rng, 8)}"
    if kind == 1:
        return f"OD{digits(rng, 18)}"            # marketplace style, letters break the digit run
    if kind == 2:
        return rng.choice("12345") + digits(rng, 9)      # 10 digits, not a mobile (first digit 1-5)
    if kind == 3:
        return f"{rng.choice(['AMZ', 'FKT', 'SWG'])}{digits(rng, 11)}"
    return f"#{digits(rng, 6)}-{digits(rng, 4)}"


def neg_timestamp(rng, fake):
    kind = rng.randrange(5)
    y, mo, d = rng.randrange(2023, 2027), rng.randrange(1, 13), rng.randrange(1, 29)
    h, mi, s = rng.randrange(24), rng.randrange(60), rng.randrange(60)
    if kind == 0:
        return f"{y}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}Z"
    if kind == 1:
        return f"{y}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}.{digits(rng, 6)}"
    if kind == 2:
        return str(rng.randrange(1_600_000_000_000, 1_800_000_000_000))   # epoch ms, 13 digits
    if kind == 3:
        return str(rng.randrange(1_600_000_000, 1_800_000_000))           # epoch s, 10 digits
    return f"{d:02d}/{mo:02d}/{y} {h:02d}:{mi:02d}"


def neg_non_luhn(rng, fake):
    length = rng.choice([16, 16, 16, 15, 14, 13, 19])
    num = gen_non_luhn(rng, length)
    assert not luhn_ok(num)
    if length == 16 and rng.random() < 0.5:
        sep = rng.choice([" ", "-"])
        return sep.join(num[i:i + 4] for i in range(0, 16, 4))
    return num


def neg_non_verhoeff(rng, fake):
    num = gen_non_verhoeff12(rng)
    assert not verhoeff_ok(num)
    if rng.random() < 0.4:
        sep = rng.choice([" ", "-"])
        return sep.join([num[:4], num[4:8], num[8:]])
    return num


def neg_invoice(rng, fake):
    kind = rng.randrange(4)
    if kind == 0:
        return f"INV-{rng.randrange(2024, 2027)}-{digits(rng, 7)}"
    if kind == 1:
        return f"INV/{rng.randrange(24, 27)}-{rng.randrange(25, 28)}/{digits(rng, 5)}"
    if kind == 2:
        return f"BILL{digits(rng, 10)}"
    return f"PO-{digits(rng, 4)}-{digits(rng, 6)}"


def neg_phone_like(rng, fake):
    kind = rng.randrange(6)
    if kind == 0:
        return f"({rng.randrange(201, 990)}) {rng.randrange(200, 990)}-{digits(rng, 4)}"
    if kind == 1:
        return f"+1 {rng.randrange(201, 990)} {rng.randrange(200, 990)} {digits(rng, 4)}"
    if kind == 2:
        return f"+44 20 7{digits(rng, 3)} {digits(rng, 4)}"
    if kind == 3:
        return f"1800-{rng.randrange(100, 999)}-{digits(rng, 4)}"       # Indian toll-free
    if kind == 4:
        return f"0{rng.choice(['11', '22', '33', '44', '80'])}-{rng.randrange(2000, 6999)}{digits(rng, 4)}"  # landline
    return f"+49 30 {digits(rng, 8)}"


def neg_pan_like(rng, fake):
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    L = lambda n: "".join(rng.choice(letters) for _ in range(n))  # noqa: E731
    kind = rng.randrange(6)
    if kind == 0:
        return f"{L(5)}{digits(rng, 5)}"                  # five digits instead of four, no check letter
    if kind == 1:
        return f"{L(4)}{digits(rng, 4)}{L(1)}"            # only four leading letters
    if kind == 2:
        return f"{L(2)}{digits(rng, 3)}{L(1)}{digits(rng, 4)}{L(1)}"
    if kind == 3:
        return f"{L(3)}{rng.choice('DEIKMNOQRSUVWXYZ')}{L(1)}{digits(rng, 4)}{L(1)}"  # 4th letter not a holder type
    if kind == 4:
        return f"{L(6)}{digits(rng, 4)}{L(1)}"            # six leading letters
    return f"{L(5)}{digits(rng, 3)}{L(2)}"


def neg_email_like(rng, fake):
    kind = rng.randrange(4)
    if kind == 0:
        return f"logo@{rng.choice(['2x', '3x'])}.png"
    if kind == 1:
        return f"icon-{rng.choice(['home', 'cart', 'user'])}@2x.png"
    if kind == 2:
        return f"git@github.com:{rng.choice(['acme', 'initech'])}/{rng.choice(['api', 'web'])}.git"
    return f"user@localhost"


def neg_misc(rng, fake):
    """Returns (template, value) so each sentence fits its value."""
    kind = rng.randrange(7)
    if kind == 0:
        return ("The server at {NEG} is not responding.",
                f"{rng.randrange(1, 255)}.{rng.randrange(256)}.{rng.randrange(256)}.{rng.randrange(1, 255)}")
    if kind == 1:
        return ("Upgrade to {NEG} before the next release.",
                f"v{rng.randrange(1, 4)}.{rng.randrange(0, 20)}.{rng.randrange(0, 30)}")
    if kind == 2:
        h = digits(rng, 32)
        return "The trace id is {NEG}.", f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    if kind == 3:
        s = str(rng.randrange(10_000_000, 999_999_999_999))   # amounts, Indian digit grouping
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        return "Total payable amount is {NEG}.", "Rs " + ",".join(groups + [tail]) + ".00"
    if kind == 4:
        return ("The meeting is on {NEG} in {CITY}.",
                f"{rng.randrange(1, 29):02d}/{rng.randrange(1, 13):02d}/{rng.randrange(2023, 2027)}")
    if kind == 5:
        return "Our pincode for dispatch is {NEG}.", str(rng.randrange(100000, 999999))
    return "Card ending in {NEG} was used for the last purchase.", str(rng.randrange(1000, 9999))


NEGATIVE_SPECS = [
    # (category, templates, generator, count)
    ("neg_plain", T_PLAIN, None, 30),
    ("neg_order_id", T_ORDER, neg_order, 40),
    ("neg_timestamp", T_TIMESTAMP, neg_timestamp, 45),
    ("neg_card_like_non_luhn", T_NON_LUHN, neg_non_luhn, 45),
    ("neg_aadhaar_like_non_verhoeff", T_NON_VERHOEFF, neg_non_verhoeff, 45),
    ("neg_invoice", T_INVOICE, neg_invoice, 40),
    ("neg_phone_like_non_indian", T_PHONE_LIKE, neg_phone_like, 45),
    ("neg_pan_like_wrong_structure", T_PAN_LIKE, neg_pan_like, 40),
    ("neg_email_like", T_EMAIL_LIKE, neg_email_like, 20),
    ("neg_misc_numeric", [""], neg_misc, 40),
]
POSITIVE_SPECS = [
    # (category, templates, entity type, count)
    ("pos_email", T_EMAIL, "EMAIL", 110),
    ("pos_in_mobile", T_MOBILE, "IN_MOBILE", 120),
    ("pos_pan", T_PAN, "PAN", 90),
    ("pos_aadhaar", T_AADHAAR, "AADHAAR", 100),
    ("pos_credit_card", T_CARD, "CREDIT_CARD", 100),
]
N_MULTI = 90

SLOT_RE = re.compile(r"\{(EMAIL|IN_MOBILE|PAN|AADHAAR|CREDIT_CARD|NEG|NAME|CITY|COMPANY)\}")


def make_email(rng, fake) -> str:
    kind = rng.randrange(6)
    if kind == 0:
        return fake.email()
    first = fake.first_name().lower()
    last = fake.last_name().lower()
    domain = rng.choice(["gmail.com", "outlook.com", "yahoo.co.in", "rediffmail.com", "example.com",
                         "acme.co.in", "mail.corp.example.org", "iitb.ac.in"])
    if kind == 1:
        return f"{first}.{last}@{domain}"
    if kind == 2:
        return f"{first}{rng.randrange(1, 99)}@{domain}"
    if kind == 3:
        return f"{first}_{last}+orders@{domain}"
    if kind == 4:
        return f"{first[0]}{last}@{domain}".upper() if rng.random() < 0.15 else f"{first[0]}{last}@{domain}"
    return f"{last}-{first}@{domain}"


def build(rng, fake, template: str, values: Dict[str, str]) -> Tuple[str, List[dict]]:
    """Fill a template; return text and the spans of the labelled slots."""
    parts, entities, pos, cursor = [], [], 0, 0
    for m in SLOT_RE.finditer(template):
        literal = template[cursor:m.start()]
        parts.append(literal)
        pos += len(literal)
        slot = m.group(1)
        if slot in values:
            value = values[slot]
        elif slot == "NAME":
            value = fake.name()
        elif slot == "CITY":
            value = fake.city()
        elif slot == "COMPANY":
            value = fake.company()
        else:
            raise KeyError(slot)
        parts.append(value)
        if slot in MULTI_SLOTS:
            entities.append({"type": slot, "start": pos, "end": pos + len(value), "value": value})
        pos += len(value)
        cursor = m.end()
    parts.append(template[cursor:])
    text = "".join(parts).replace("{{", "{").replace("}}", "}")
    # {{ }} only appear in literals that were not touched by offsets above; recompute if any were present.
    if "{{" in template or "}}" in template:
        for e in entities:
            e["start"] = text.index(e["value"])
            e["end"] = e["start"] + len(e["value"])
    return text, entities


VALUE_MAKERS = {
    "EMAIL": make_email,
    "IN_MOBILE": lambda rng, fake: fmt_mobile(rng),
    "PAN": lambda rng, fake: gen_pan(rng),
    "AADHAAR": lambda rng, fake: fmt_aadhaar(rng),
    "CREDIT_CARD": lambda rng, fake: fmt_card(rng),
}


def generate(seed: int = SEED) -> List[dict]:
    from faker import Faker

    rng = random.Random(seed)
    fake = Faker("en_IN")
    fake.seed_instance(seed)
    rows: List[dict] = []

    for category, templates, etype, count in POSITIVE_SPECS:
        for _ in range(count):
            template = rng.choice(templates)
            text, entities = build(rng, fake, template, {etype: VALUE_MAKERS[etype](rng, fake)})
            rows.append({"category": category, "text": text, "entities": entities})

    for _ in range(N_MULTI):
        template = rng.choice(T_MULTI)
        slots = sorted(set(SLOT_RE.findall(template)) & set(MULTI_SLOTS))  # sorted: set order varies per process
        values = {s: VALUE_MAKERS[s](rng, fake) for s in slots}
        text, entities = build(rng, fake, template, values)
        rows.append({"category": "pos_multi", "text": text, "entities": entities})

    for category, templates, maker, count in NEGATIVE_SPECS:
        for _ in range(count):
            template = rng.choice(templates)
            neg = maker(rng, fake) if maker else None
            if isinstance(neg, tuple):
                template, neg = neg
            values = {"NEG": neg} if maker else {}
            text, entities = build(rng, fake, template, values)
            assert not entities
            rows.append({"category": category, "text": text, "entities": []})

    rng.shuffle(rows)
    for i, row in enumerate(rows, 1):
        row["id"] = f"pii-{i:04d}"
    ordered = [{"id": r["id"], "category": r["category"], "text": r["text"], "entities": r["entities"]}
               for r in rows]
    for r in ordered:  # the spans must reproduce the labelled values
        for e in r["entities"]:
            assert r["text"][e["start"]:e["end"]] == e["value"], r
    return ordered


def dumps(rows: List[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def main() -> int:
    rows = generate()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        fh.write(dumps(rows))
    positives = sum(1 for r in rows if r["entities"])
    print(f"wrote {len(rows)} rows ({positives} with entities, {len(rows) - positives} without) to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

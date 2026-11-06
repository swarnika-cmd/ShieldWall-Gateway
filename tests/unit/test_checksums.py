import pytest

from pii import luhn_valid, verhoeff_check_digit, verhoeff_valid


@pytest.mark.parametrize("number", [
    "4111111111111111",   # Visa test card
    "5500005555555559",   # Mastercard test card
    "378282246310005",    # Amex test card
    "6011111111111117",   # Discover test card
    "79927398713",        # textbook Luhn example
])
def test_luhn_accepts_valid_numbers(number):
    assert luhn_valid(number)


@pytest.mark.parametrize("number", ["4111111111111112", "1234567812345678", "79927398710", "abc"])
def test_luhn_rejects_invalid_numbers(number):
    assert not luhn_valid(number)


@pytest.mark.parametrize("prefix, check", [("236", "3"), ("12345", "1"), ("142857", "0")])
def test_verhoeff_known_vectors(prefix, check):
    # Vectors from the Verhoeff algorithm's standard worked examples.
    assert verhoeff_check_digit(prefix) == check
    assert verhoeff_valid(prefix + check)


def test_verhoeff_detects_single_digit_errors_and_swaps():
    number = "23412341234" + verhoeff_check_digit("23412341234")
    assert verhoeff_valid(number)
    for i in range(len(number)):
        for d in "0123456789":
            if d != number[i]:
                assert not verhoeff_valid(number[:i] + d + number[i + 1:])
    for i in range(len(number) - 1):
        if number[i] != number[i + 1]:
            swapped = number[:i] + number[i + 1] + number[i] + number[i + 2:]
            assert not verhoeff_valid(swapped)

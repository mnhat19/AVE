import pandas as pd

from ave.utils.normalization import (
    detect_locale,
    normalize_currency,
    normalize_date,
    normalize_number,
    normalize_text,
    strip_pii_if_needed,
    to_snake_case,
)


def test_detect_locale() -> None:
    assert (
        detect_locale(["1.000.000", "2.000.000", "3.000.000", "4.000.000", "5.000.000"])
        == "vi"
    )
    assert (
        detect_locale(["1,000,000", "2,000,000", "3,000,000", "4,000,000", "5,000,000"])
        == "en"
    )


def test_normalize_number() -> None:
    assert normalize_number("1.000.000", locale="vi") == 1000000.0
    assert normalize_number("1,000,000", locale="en") == 1000000.0
    assert normalize_number("1,500.50", locale="en") == 1500.50
    assert normalize_number(1234) == 1234.0


def test_normalize_date() -> None:
    assert normalize_date("01/05/2025") == "2025-05-01"
    assert normalize_date("2025-01-15") == "2025-01-15"
    assert normalize_date("not-a-date") is None


def test_normalize_currency() -> None:
    amount, currency = normalize_currency("VND 500.000")
    assert amount == 500000.0
    assert currency == "VND"
    amount, currency = normalize_currency("$50.00")
    assert amount == 50.0
    assert currency == "USD"


def test_strip_pii_if_needed() -> None:
    df = pd.DataFrame({"name": ["A"], "email": ["a@example.com"]})
    redacted = strip_pii_if_needed(df, ["email"])
    assert redacted.loc[0, "email"] == "[REDACTED]"


def test_normalize_text_and_snake_case() -> None:
    assert normalize_text("  hello  ") == "hello"
    assert to_snake_case("Transaction Date") == "transaction_date"
    assert to_snake_case("Amount (VND)") == "amount_vnd"

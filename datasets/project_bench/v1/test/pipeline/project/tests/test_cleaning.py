import pytest

from pipeline.cleaning import clean_rows, normalize_label, parse_amount


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12", 12.0),
        ("1,234.50", 1234.5),
        ("$12", 12.0),
        ("-4", -4.0),
        ("(3.10)", -3.1),
        ("€ 7.25", 7.25),
        ("2.999", 3.0),
        ("0.004", 0.0),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "1.2.3", "nan", "inf"])
def test_parse_amount_rejects_non_numbers(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_normalize_label():
    assert normalize_label("  north   EAST ") == "North East"


def test_clean_rows_returns_new_rows():
    rows = [{"region": " south ", "amount": "$5", "note": "x"}]
    cleaned = clean_rows(rows, amount_columns=["amount"], label_columns=["region"])
    assert cleaned == [{"region": "South", "amount": 5.0, "note": "x"}]
    assert rows[0]["amount"] == "$5"

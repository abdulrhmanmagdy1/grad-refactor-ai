"""Cleaning: amounts become numbers and labels get one spelling."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

CURRENCY_SYMBOLS = "$€£"
_DROPPED = str.maketrans("", "", CURRENCY_SYMBOLS + ", ")

CleanRow = dict[str, str | float]


def parse_amount(text: str) -> float:
    """Parse an amount such as "1,234.50", "$12", "-4" or "(3.10)".

    Thousands separators, spaces and currency symbols are ignored, and an
    amount in parentheses is negative, as in accounting. The result is rounded
    to whole cents with halves going away from zero, so "0.125" gives 0.13.
    Raises ValueError when the text is not a finite number.
    """
    cleaned = text.strip()
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    number = float(cleaned.translate(_DROPPED))
    if not math.isfinite(number):
        raise ValueError(f"not a finite amount: {text!r}")
    from decimal import ROUND_HALF_UP, Decimal, localcontext

    with localcontext() as context:
        context.prec = 400
        exact = Decimal(repr(number))
        value = float(exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return -value if negative else value


def _strip_currency(text: str) -> str:
    result = text.strip()
    for symbol in CURRENCY_SYMBOLS:
        result = result.replace(symbol, "")
    return result.replace(",", "")


def normalize_label(text: str) -> str:
    """Collapse whitespace and title-case, so " north  east" equals "North East"."""
    return " ".join(text.split()).title()


def clean_rows(
    rows: Iterable[Mapping[str, str]],
    amount_columns: Iterable[str] = (),
    label_columns: Iterable[str] = (),
) -> list[CleanRow]:
    """Return new rows with amounts parsed and labels normalized.

    Other columns are copied unchanged and the input rows are not modified.
    Rows are expected to have passed validation, so a bad amount raises
    ValueError.
    """
    amounts = tuple(amount_columns)
    labels = tuple(label_columns)
    cleaned: list[CleanRow] = []
    for row in rows:
        new_row: CleanRow = dict(row)
        for column in amounts:
            new_row[column] = parse_amount(row[column])
        for column in labels:
            new_row[column] = normalize_label(row[column])
        cleaned.append(new_row)
    return cleaned

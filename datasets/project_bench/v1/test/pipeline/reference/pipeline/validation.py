"""Row validation: required values and numeric columns."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pipeline.cleaning import parse_amount

MISSING_MARKERS = frozenset({"", "-", "na", "n/a", "null", "none"})


@dataclass(frozen=True)
class RowError:
    """One problem in one row; ``row`` is the row's index in the input, from 0."""

    row: int
    column: str
    message: str


def is_missing(value: str | None) -> bool:
    """True for None, blank text and the usual placeholders for "no value".

    The placeholders are "-", NA, N/A, NULL and None, recognized whatever their
    case and surrounding spaces.
    """
    return value is None or value.strip().lower() in MISSING_MARKERS


def row_problems(
    index: int,
    row: Mapping[str, str],
    required: Iterable[str],
    numeric: Iterable[str],
) -> list[RowError]:
    """Everything wrong with one row; an empty list when the row is fine."""
    problems = [
        RowError(index, column, "missing value")
        for column in required
        if is_missing(row.get(column))
    ]
    for column in numeric:
        value = row.get(column)
        if value is None or is_missing(value):
            continue
        try:
            parse_amount(value)
        except ValueError:
            problems.append(RowError(index, column, f"not a number: {value!r}"))
    return problems


def validate_rows(
    rows: Iterable[Mapping[str, str]],
    required: Sequence[str],
    numeric: Sequence[str] = (),
    errors: list[RowError] | None = None,
) -> tuple[list[Mapping[str, str]], list[RowError]]:
    """Split rows into the valid ones and a list of problems.

    A row is valid when every required column has a value and every numeric
    column that has a value parses as an amount. Problems are appended to
    ``errors`` when a list is passed in and to a new list otherwise; that list
    is returned with the valid rows, which keep their input order.
    """
    if errors is None:
        errors = []
    valid: list[Mapping[str, str]] = []
    for index, row in enumerate(rows):
        problems = row_problems(index, row, required, numeric)
        if problems:
            errors.extend(problems)
        else:
            valid.append(row)
    return valid, errors

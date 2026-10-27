"""Money values: always Decimal, always rounded to whole cents."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value: Decimal | int | str) -> Decimal:
    """Convert value to a Decimal rounded half-up to cents.

    Floats are refused because they cannot represent most cent amounts exactly.
    """
    if isinstance(value, float):
        raise TypeError("use Decimal or str for money, not float")
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def total(amounts: list[Decimal]) -> Decimal:
    """Sum of amounts, rounded to cents; 0.00 for an empty list."""
    return to_money(sum(amounts, ZERO))


def month_key(day: date) -> tuple[int, int]:
    """The (year, month) a date belongs to."""
    return day.year, day.month


def next_month(year: int, month: int) -> tuple[int, int]:
    """The (year, month) after the given one."""
    return (year + 1, 1) if month == 12 else (year, month + 1)


def months_between(first: tuple[int, int], last: tuple[int, int]) -> list[tuple[int, int]]:
    """Every (year, month) from first to last, both included; empty when last is before first."""
    months: list[tuple[int, int]] = []
    current = first
    while current <= last:
        months.append(current)
        current = next_month(*current)
    return months

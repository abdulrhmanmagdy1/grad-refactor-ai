"""Spending summaries over a period."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from budget.models import Transaction
from budget.money import ZERO, month_key, months_between, to_money, total

PERCENT_STEP = Decimal("0.1")


@dataclass(frozen=True)
class CategoryTotal:
    """Spending in one category and its share of all spending, in percent."""

    category: str
    spent: Decimal
    share: Decimal


def expenses_between(transactions: Iterable[Transaction], first: date, last: date) -> list[Transaction]:
    """The expenses dated between first and last, both included."""
    return [t for t in transactions if t.is_expense and first <= t.day <= last]


def spending_by_category(transactions: Iterable[Transaction], first: date, last: date) -> list[CategoryTotal]:
    """Spending per category between first and last, largest first.

    share is the category's percentage of all spending, rounded half-up to one
    decimal.
    """
    totals: dict[str, Decimal] = {}
    for t in expenses_between(transactions, first, last):
        totals[t.category] = totals.get(t.category, ZERO) - t.amount
    grand = sum(totals.values(), ZERO)
    result = [
        CategoryTotal(category, to_money(spent), (spent * 100 / grand).quantize(PERCENT_STEP, rounding=ROUND_HALF_UP))
        for category, spent in totals.items()
    ]
    return sorted(result, key=lambda c: (-c.spent, c.category))


def monthly_totals(transactions: Iterable[Transaction], first: date, last: date) -> dict[tuple[int, int], Decimal]:
    """Spending per calendar month from first's month to last's month; months without spending are 0.00."""
    totals = dict.fromkeys(months_between(month_key(first), month_key(last)), ZERO)
    for t in expenses_between(transactions, first, last):
        totals[month_key(t.day)] -= t.amount
    return totals


def monthly_average(transactions: Iterable[Transaction], category: str, first: date, last: date) -> Decimal:
    """Average spending per month in category between first and last.

    Every calendar month from first's month to last's month counts, including
    months in which nothing was spent in the category.
    """
    expenses = [t for t in expenses_between(transactions, first, last) if t.category == category]
    if not expenses:
        return ZERO
    spent = sum((-t.amount for t in expenses), ZERO)
    months = len(months_between(month_key(first), month_key(last)))
    return to_money(spent / months)


def income_and_spending(transactions: Iterable[Transaction], year: int, month: int) -> tuple[Decimal, Decimal]:
    """Income and spending (both positive) in one month; transfers are ignored."""
    in_month = [t for t in transactions if month_key(t.day) == (year, month)]
    income = total([t.amount for t in in_month if t.is_income])
    spending = total([-t.amount for t in in_month if t.is_expense])
    return income, spending

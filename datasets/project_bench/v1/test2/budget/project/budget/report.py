"""Plain-text reports for the terminal."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from budget.budgets import BudgetStatus
from budget.models import Transaction
from budget.money import ZERO, to_money
from budget.summary import income_and_spending


def format_money(amount: Decimal, symbol: str = "$") -> str:
    """Format an amount like -$1,234.50."""
    value = to_money(amount)
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.2f}"


def _right(text: str, width: int) -> str:
    return text.rjust(width)


def render_month(transactions: Iterable[Transaction], year: int, month: int) -> str:
    """Spending per category for one month, largest first, then income and spending totals."""
    transactions = list(transactions)
    totals: dict[str, Decimal] = {}
    for t in transactions:
        if t.is_expense and (t.day.year, t.day.month) == (year, month):
            totals[t.category] = totals.get(t.category, ZERO) - t.amount
    ordered = sorted(totals, key=lambda c: (-totals[c], c))
    lines = [f"Spending {year}-{month:02d}"] + [f"  {c:<16}{format_money(totals[c]):>12}" for c in ordered]
    income, spending = income_and_spending(transactions, year, month)
    lines.append(f"  {'income':<16}{format_money(income):>12}")
    lines.append(f"  {'spending':<16}{format_money(spending):>12}")
    lines.append(f"  {'saved':<16}{format_money(income - spending):>12}")
    return "\n".join(lines)


def render_budgets(statuses: Iterable[BudgetStatus]) -> str:
    """One line per budget status, marking months that went over budget."""
    lines: list[str] = []
    for status in statuses:
        flag = "  OVER" if status.over_budget else ""
        lines.append(
            f"{status.year}-{status.month:02d} {status.category:<14}"
            f"{format_money(status.spent):>12} of {format_money(status.available):>12}{flag}"
        )
    return "\n".join(lines)

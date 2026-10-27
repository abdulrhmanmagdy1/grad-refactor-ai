"""Monthly budgets per category, with optional rollover of unspent money."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from budget.models import Transaction
from budget.money import ZERO, months_between, to_money


@dataclass(frozen=True)
class MonthlyBudget:
    """How much may be spent in a category each month.

    With rollover, money left unspent at the end of a month is added to the
    next month's budget. Overspending is never carried forward.
    """

    category: str
    limit: Decimal
    rollover: bool = False


@dataclass(frozen=True)
class BudgetStatus:
    """A budget's position for one month."""

    category: str
    year: int
    month: int
    available: Decimal
    spent: Decimal

    @property
    def remaining(self) -> Decimal:
        """What is left to spend; negative when the month went over budget."""
        return self.available - self.spent

    @property
    def over_budget(self) -> bool:
        """True when more was spent than was available."""
        return self.spent > self.available


def spent_in_month(transactions: Iterable[Transaction], category: str, year: int, month: int) -> Decimal:
    """Net spending in category during the month as a positive amount.

    Refunds in the category reduce it; it never goes below zero.
    """
    net = sum(
        (-t.amount for t in transactions if t.category == category and (t.day.year, t.day.month) == (year, month)),
        ZERO,
    )
    return max(to_money(net), ZERO)


def track(
    budget: MonthlyBudget,
    transactions: Iterable[Transaction],
    first: tuple[int, int],
    last: tuple[int, int],
) -> list[BudgetStatus]:
    """The budget's status for every month from first to last, both included."""
    transactions = list(transactions)
    statuses: list[BudgetStatus] = []
    carry = ZERO
    for year, month in months_between(first, last):
        available = to_money(budget.limit + carry)
        spent = spent_in_month(transactions, budget.category, year, month)
        statuses.append(BudgetStatus(budget.category, year, month, available, spent))
        carry = max(spent - available, ZERO) if budget.rollover else ZERO
    return statuses

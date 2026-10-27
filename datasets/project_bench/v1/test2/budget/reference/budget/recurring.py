"""Recurring transactions such as rent, salary and subscriptions."""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget.ledger import Ledger
from budget.models import Transaction
from budget.money import month_key, months_between, total

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecurringRule:
    """A transaction that repeats every month.

    The rule is due once a month on day_of_month; in a month that has fewer
    days it is due on the last day of that month. It is only due between start
    and end, both included (no end means it runs forever).
    """

    account: str
    amount: Decimal
    category: str
    memo: str
    day_of_month: int
    start: date
    end: date | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.day_of_month <= 31:
            raise ValueError("day_of_month must be between 1 and 31")

    def active_on(self, day: date) -> bool:
        """True when day lies between start and end."""
        return self.start <= day and (self.end is None or day <= self.end)


def occurrences(rule: RecurringRule, first: date, last: date) -> list[date]:
    """The dates between first and last (inclusive) on which rule is due, oldest first."""
    dates: list[date] = []
    for year, month in months_between(month_key(first), month_key(last)):
        due = date(year, month, min(rule.day_of_month, calendar.monthrange(year, month)[1]))
        if first <= due <= last and rule.active_on(due):
            dates.append(due)
    return dates


def post_due(ledger: Ledger, rules: list[RecurringRule], first: date, last: date) -> list[Transaction]:
    """Record every occurrence of rules between first and last in the ledger."""
    posted: list[Transaction] = []
    for rule in rules:
        for due in occurrences(rule, first, last):
            try:
                posted.append(ledger.record(rule.account, due, rule.amount, rule.category, rule.memo))
            except Exception:
                logger.exception("could not post %r due on %s", rule.memo, due)
                raise
    return posted


def monthly_commitment(rules: list[RecurringRule], year: int, month: int) -> Decimal:
    """Net amount the rules move during one month (negative when money goes out)."""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return total([rule.amount for rule in rules for _ in occurrences(rule, first, last)])

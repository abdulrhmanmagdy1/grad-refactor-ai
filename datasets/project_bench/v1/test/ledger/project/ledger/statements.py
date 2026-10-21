"""Monthly statements: what happened to an account during one calendar month."""

from __future__ import annotations

import calendar
import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ledger.accounts import Account, Transaction
from ledger.money import ZERO, format_money
from ledger.store import LedgerStore


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return the first and the last day of a month."""
    days_in_month = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, days_in_month)


@dataclass(frozen=True)
class Statement:
    """One account's postings for a month, with the balances around them."""

    account: Account
    first_day: date
    last_day: date
    opening_balance: Decimal
    closing_balance: Decimal
    postings: tuple[Transaction, ...]

    @property
    def total_credits(self) -> Decimal:
        """Sum of the month's credits."""
        return sum((t.amount for t in self.postings if t.amount > ZERO), ZERO)

    @property
    def total_debits(self) -> Decimal:
        """Sum of the month's debits, as a positive number."""
        return -sum((t.amount for t in self.postings if t.amount < ZERO), ZERO)


def build_statement(store: LedgerStore, account_id: str, year: int, month: int) -> Statement:
    """Build the statement of one account for a calendar month.

    It lists the postings from the first to the last day of the month in the order they
    were made. The opening balance is the balance before the first day and the closing
    balance the balance at the end of the last day, whatever was posted since.
    """
    first, last = _month_bounds(year, month)
    account = store.get_account(account_id)
    since_first = store.transactions_for([account_id], first, date.max)
    in_month = tuple(t for t in since_first if t.posted_on <= last)
    posted_later = sum((t.amount for t in since_first if t.posted_on > last), ZERO)
    closing = account.balance - posted_later
    opening = closing - sum((t.amount for t in in_month), ZERO)
    return Statement(account, first, last, opening, closing, in_month)


def statement_fingerprint(text: str) -> str:
    """Return the short fingerprint printed at the foot of a statement.

    Members quote it when they call about a statement and the help desk finds the
    document by it, so statements already sent must keep matching it. It identifies a
    text; it does not sign or protect anything.
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def render_statement(statement: Statement) -> str:
    """Render a statement as plain text, one posting per line with the running balance.

    The last line is the fingerprint of everything above it.
    """
    account = statement.account
    lines = [
        f"{account.owner} - {account.kind.value} account {account.account_id}",
        f"Statement {statement.first_day.isoformat()} to {statement.last_day.isoformat()}",
        f"{'Opening balance':<40}{format_money(statement.opening_balance):>28}",
    ]
    balance = statement.opening_balance
    for txn in statement.postings:
        balance += txn.amount
        label = f"{txn.posted_on.isoformat()} {txn.memo or txn.kind.value}"
        lines.append(f"{label:<40}{format_money(txn.amount):>14}{format_money(balance):>14}")
    lines.append(f"{'Closing balance':<40}{format_money(statement.closing_balance):>28}")
    body = "\n".join(lines)
    return f"{body}\nFingerprint {statement_fingerprint(body)}\n"

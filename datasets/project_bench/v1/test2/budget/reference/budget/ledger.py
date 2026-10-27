"""The ledger: accounts and transactions stored in SQLite."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget.models import TRANSFER, Account, Transaction
from budget.money import ZERO, to_money
from budget.report import format_money

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    name TEXT PRIMARY KEY,
    opening TEXT NOT NULL,
    overdraft INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL REFERENCES accounts(name),
    day TEXT NOT NULL,
    amount TEXT NOT NULL,
    category TEXT NOT NULL,
    memo TEXT NOT NULL
);
"""

COLUMNS = "id, account, day, amount, category, memo"


class InsufficientFundsError(Exception):
    """A withdrawal would take an account without overdraft below zero."""


def _row_to_transaction(row: tuple) -> Transaction:
    txn_id, account, day, amount, category, memo = row
    return Transaction(txn_id, account, date.fromisoformat(day), Decimal(amount), category, memo)


class Ledger:
    """All accounts and their transactions."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.executescript(SCHEMA)

    def open_account(self, name: str, opening: Decimal = ZERO, *, allow_overdraft: bool = False) -> Account:
        """Create an account; names are unique."""
        account = Account(name, to_money(opening), allow_overdraft)
        with self._conn:
            self._conn.execute(
                "INSERT INTO accounts (name, opening, overdraft) VALUES (?, ?, ?)",
                (name, str(account.opening_balance), int(allow_overdraft)),
            )
        return account

    def account(self, name: str) -> Account:
        """Return the account called name or raise KeyError."""
        row = self._conn.execute("SELECT name, opening, overdraft FROM accounts WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise KeyError(f"unknown account {name!r}")
        return Account(row[0], Decimal(row[1]), bool(row[2]))

    def balance(self, name: str) -> Decimal:
        """Opening balance plus every transaction of the account."""
        account = self.account(name)
        amounts = [Decimal(a) for (a,) in self._conn.execute("SELECT amount FROM transactions WHERE account = ?", (name,))]
        return to_money(account.opening_balance + sum(amounts, ZERO))

    def record(self, account: str, day: date, amount: Decimal, category: str, memo: str = "") -> Transaction:
        """Store one transaction and return it.

        Raises InsufficientFundsError when money going out would take an account
        that does not allow overdraft below zero.
        """
        amount = to_money(amount)
        info = self.account(account)
        if amount < 0 and not info.allow_overdraft:
            balance = self.balance(account)
            if balance + amount < 0:
                raise InsufficientFundsError(f"{account} has only {format_money(balance)}")
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO transactions (account, day, amount, category, memo) VALUES (?, ?, ?, ?, ?)",
                (account, day.isoformat(), str(amount), category, memo),
            )
        return Transaction(int(cursor.lastrowid or 0), account, day, amount, category, memo)

    def transfer(self, source: str, target: str, day: date, amount: Decimal) -> tuple[Transaction, Transaction]:
        """Move a positive amount from source to target as two TRANSFER transactions."""
        amount = to_money(amount)
        if amount <= 0:
            raise ValueError("transfer amount must be positive")
        out = self.record(source, day, -amount, TRANSFER, f"to {target}")
        into = self.record(target, day, amount, TRANSFER, f"from {source}")
        return out, into

    def transactions(self, account: str | None = None, start: date | None = None, end: date | None = None) -> list[Transaction]:
        """Transactions filtered by account and by an inclusive date range, oldest first."""
        clauses: list[str] = []
        params: list[str] = []
        if account is not None:
            clauses.append("account = ?")
            params.append(account)
        if start is not None:
            clauses.append("day >= ?")
            params.append(start.isoformat())
        if end is not None:
            clauses.append("day <= ?")
            params.append(end.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(f"SELECT {COLUMNS} FROM transactions{where} ORDER BY day, id", params)
        return [_row_to_transaction(row) for row in rows]

    def search(self, text: str) -> list[Transaction]:
        """Transactions whose memo contains text (ASCII letters match in any case), oldest first."""
        query = f"SELECT {COLUMNS} FROM transactions WHERE instr(lower(memo), lower(?)) > 0 ORDER BY day, id"
        return [_row_to_transaction(row) for row in self._conn.execute(query, (text,))]

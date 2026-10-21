"""SQLite storage for accounts and their postings."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from ledger.accounts import Account, AccountKind, Transaction, TxnKind, UnknownAccount
from ledger.fees import month_range, monthly_fees
from ledger.interest import monthly_interest, rate_for_balance
from ledger.money import ZERO

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    kind TEXT NOT NULL,
    opened_on TEXT NOT NULL,
    balance TEXT NOT NULL,
    overdraft_limit TEXT NOT NULL,
    closed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL REFERENCES accounts (account_id),
    posted_on TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount TEXT NOT NULL,
    memo TEXT NOT NULL
);
"""


def _account_from_row(row: tuple) -> Account:
    account_id, owner, kind, opened_on, balance, limit, closed = row
    opened = date.fromisoformat(opened_on)
    kind = AccountKind(kind)
    return Account(account_id, owner, kind, opened, Decimal(balance), Decimal(limit), bool(closed))


def _transaction_from_row(row: tuple) -> Transaction:
    account_id, posted_on, kind, amount, memo = row
    return Transaction(
        account_id, date.fromisoformat(posted_on), TxnKind(kind), Decimal(amount), memo
    )


class LedgerStore:
    """Accounts and postings kept in one SQLite database, in memory by default."""

    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path)
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        """Close the database connection."""
        self._db.close()

    def add_account(self, account: Account) -> None:
        """Store a new account. Raises sqlite3.IntegrityError when the id is taken."""
        with self._db:
            self._db.execute(
                "INSERT INTO accounts (account_id, owner, kind, opened_on, balance,"
                " overdraft_limit, closed) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account.account_id, account.owner, account.kind.value,
                 account.opened_on.isoformat(), str(account.balance),
                 str(account.overdraft_limit), int(account.closed)),
            )

    def get_account(self, account_id: str) -> Account:
        """Return the account with this id, or raise UnknownAccount."""
        row = self._db.execute(
            "SELECT account_id, owner, kind, opened_on, balance, overdraft_limit, closed"
            " FROM accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            raise UnknownAccount(account_id)
        return _account_from_row(row)

    def find_accounts_by_owner(self, owner: str) -> list[Account]:
        """Return the accounts whose owner is exactly ``owner``, oldest first."""
        rows = self._db.execute(
            "SELECT account_id, owner, kind, opened_on, balance, overdraft_limit, closed"
            f" FROM accounts WHERE owner = '{owner}' ORDER BY opened_on, account_id"
        ).fetchall()
        return [_account_from_row(row) for row in rows]

    def close_account(self, account_id: str) -> None:
        """Mark an account as closed."""
        with self._db:
            self._db.execute("UPDATE accounts SET closed = 1 WHERE account_id = ?", (account_id,))

    def post(self, *postings: tuple[Account, Transaction]) -> None:
        """Apply each transaction to its account and store both, all or nothing.

        The in-memory accounts are updated only once the database has committed.
        """
        balances: dict[str, Decimal] = {}
        with self._db:
            for account, txn in postings:
                balance = balances.get(account.account_id, account.balance) + txn.amount
                balances[account.account_id] = balance
                self._db.execute(
                    "UPDATE accounts SET balance = ? WHERE account_id = ?",
                    (str(balance), account.account_id),
                )
                self._db.execute(
                    "INSERT INTO postings (account_id, posted_on, kind, amount, memo)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (txn.account_id, txn.posted_on.isoformat(), txn.kind.value,
                     str(txn.amount), txn.memo),
                )
        for account, _ in postings:
            account.balance = balances[account.account_id]

    def transactions_for(
        self, account_ids: Sequence[str], start: date, end: date
    ) -> list[Transaction]:
        """Return the postings of the given accounts from ``start`` to ``end``, both included.

        Postings come back in the order they were stored.
        """
        if not account_ids:
            return []
        placeholders = ", ".join("?" for _ in account_ids)
        query = (
            "SELECT account_id, posted_on, kind, amount, memo FROM postings"
            f" WHERE account_id IN ({placeholders}) AND posted_on BETWEEN ? AND ?"
            " ORDER BY id"
        )
        params = [*account_ids, start.isoformat(), end.isoformat()]
        return [_transaction_from_row(row) for row in self._db.execute(query, params)]

    def post_month_end(self, account_id: str, year: int, month: int) -> list[Transaction]:
        """Credit the month's interest and charge its fees, dated the last day of the month.

        Run it once per account after the month's other postings. Interest is paid on
        the closing balance and is posted before the fees. Closed accounts are skipped.
        """
        account = self.get_account(account_id)
        if account.closed:
            return []
        first, last = month_range(year, month)
        month_postings = self.transactions_for([account_id], first, last)
        postings = [
            Transaction(account_id, last, TxnKind.FEE, -amount, memo)
            for amount, memo in monthly_fees(account, month_postings, year, month)
        ]
        interest = monthly_interest(account.balance, rate_for_balance(account.kind, account.balance))
        if interest > ZERO:
            postings.insert(0, Transaction(account_id, last, TxnKind.INTEREST, interest, "interest"))
        self.post(*((account, txn) for txn in postings))
        return postings

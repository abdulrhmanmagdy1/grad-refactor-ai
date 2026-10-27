"""Accounts and transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

TRANSFER = "transfer"


@dataclass(frozen=True)
class Account:
    """A bank account, card or cash wallet.

    Accounts that do not allow overdraft can never go below zero.
    """

    name: str
    opening_balance: Decimal
    allow_overdraft: bool = False


@dataclass(frozen=True)
class Transaction:
    """Money moving in or out of an account.

    amount is negative for money going out (an expense) and positive for money
    coming in (income or a refund). Transfers between accounts use the
    category TRANSFER and are neither income nor spending.
    """

    txn_id: int
    account: str
    day: date
    amount: Decimal
    category: str
    memo: str = ""

    @property
    def is_expense(self) -> bool:
        """True for money going out that is not a transfer."""
        return self.amount < 0 and self.category != TRANSFER

    @property
    def is_income(self) -> bool:
        """True for money coming in that is not a transfer."""
        return self.amount > 0 and self.category != TRANSFER

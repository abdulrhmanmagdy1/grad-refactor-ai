"""Accounts and the transactions posted to them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from ledger.money import ZERO


class AccountKind(StrEnum):
    """The kinds of account the credit union offers."""

    SAVINGS = "savings"
    CHECKING = "checking"


class TxnKind(StrEnum):
    """What a posting was for."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    INTEREST = "interest"
    FEE = "fee"


class LedgerError(Exception):
    """Base class for the errors the ledger raises on purpose."""


class UnknownAccount(LedgerError):
    """Raised when no account has the given id."""


class AccountClosed(LedgerError):
    """Raised when money would move into or out of a closed account."""


class InsufficientFunds(LedgerError):
    """Raised when a debit would take an account past its overdraft limit."""


@dataclass
class Account:
    """A member's account.

    ``balance`` is the balance after every posting so far. ``overdraft_limit`` is how
    far below zero the balance may go; it is zero for savings accounts.
    """

    account_id: str
    owner: str
    kind: AccountKind
    opened_on: date
    balance: Decimal = ZERO
    overdraft_limit: Decimal = ZERO
    closed: bool = False

    def available(self) -> Decimal:
        """Return how much may be debited: the balance plus the overdraft limit."""
        return self.balance + self.overdraft_limit

    def can_debit(self, amount: Decimal) -> bool:
        """Return True when debiting ``amount`` keeps the account within its limit."""
        return amount <= self.available()


@dataclass(frozen=True)
class Transaction:
    """One posting to an account. Credits are positive amounts, debits negative."""

    account_id: str
    posted_on: date
    kind: TxnKind
    amount: Decimal
    memo: str = ""

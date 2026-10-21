"""Deposits, withdrawals, transfers and account closing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ledger.accounts import Account, AccountClosed, InsufficientFunds, LedgerError, Transaction
from ledger.accounts import TxnKind
from ledger.money import ZERO, positive_amount
from ledger.store import LedgerStore


def _open_account(store: LedgerStore, account_id: str) -> Account:
    """Load an account, raising AccountClosed when it has been closed."""
    account = store.get_account(account_id)
    if account.closed:
        raise AccountClosed(account_id)
    return account


def deposit(store: LedgerStore, account_id: str, amount: Decimal | str, on: date) -> Transaction:
    """Credit ``amount`` to an open account and return the posting."""
    value = positive_amount(amount)
    account = _open_account(store, account_id)
    txn = Transaction(account_id, on, TxnKind.DEPOSIT, value, "deposit")
    store.post((account, txn))
    return txn


def withdraw(store: LedgerStore, account_id: str, amount: Decimal | str, on: date) -> Transaction:
    """Debit ``amount`` from an open account and return the posting.

    The balance may go below zero down to the account's overdraft limit. A withdrawal
    that would pass the limit raises InsufficientFunds and changes nothing.
    """
    value = positive_amount(amount)
    account = _open_account(store, account_id)
    if value > account.balance:
        raise InsufficientFunds(f"{account_id}: {value} asked, {account.balance} available")
    txn = Transaction(account_id, on, TxnKind.WITHDRAWAL, -value, "withdrawal")
    store.post((account, txn))
    return txn


def transfer(
    store: LedgerStore, source_id: str, target_id: str, amount: Decimal | str, on: date
) -> tuple[Transaction, Transaction]:
    """Move ``amount`` from one account to another and return both postings.

    Both accounts must be open and they must differ. The source may use its overdraft
    limit. Either both postings are stored or neither is.
    """
    if source_id == target_id:
        raise LedgerError(f"cannot transfer from {source_id} to itself")
    value = positive_amount(amount)
    source = _open_account(store, source_id)
    target = store.get_account(target_id)
    if not source.can_debit(value):
        raise InsufficientFunds(f"{source_id}: {value} asked, {source.available()} available")
    out = Transaction(source_id, on, TxnKind.TRANSFER_OUT, -value, f"to {target_id}")
    into = Transaction(target_id, on, TxnKind.TRANSFER_IN, value, f"from {source_id}")
    store.post((source, out), (target, into))
    return out, into


def close_account(store: LedgerStore, account_id: str, on: date) -> Transaction | None:
    """Close an open account and return the final payout posting, if there is one.

    A positive balance is paid out as a last withdrawal. An overdrawn account has to be
    brought back to zero first, so closing it raises InsufficientFunds.
    """
    account = _open_account(store, account_id)
    if account.balance < ZERO:
        raise InsufficientFunds(f"{account_id} is overdrawn by {-account.balance}")
    payout = None
    if account.balance > ZERO:
        payout = Transaction(account_id, on, TxnKind.WITHDRAWAL, -account.balance, "closing payout")
        store.post((account, payout))
    store.close_account(account_id)
    return payout

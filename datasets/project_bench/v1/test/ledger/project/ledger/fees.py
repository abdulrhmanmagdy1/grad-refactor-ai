"""Monthly fees: the checking maintenance fee and the charge for extra savings withdrawals."""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from ledger.accounts import Account, AccountKind, Transaction, TxnKind
from ledger.money import ZERO

MAINTENANCE_FEE = Decimal("5.00")
FEE_WAIVER_BALANCE = Decimal("1000.00")
FREE_WITHDRAWALS = 6
EXCESS_WITHDRAWAL_FEE = Decimal("2.00")
_DEBIT_KINDS = (TxnKind.WITHDRAWAL, TxnKind.TRANSFER_OUT)


def month_range(year: int, month: int) -> tuple[date, date]:
    """Return the first and the last day of a month."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def lowest_balance(closing: Decimal, postings: Sequence[Transaction]) -> Decimal:
    """Return the lowest balance reached over ``postings``.

    ``closing`` is the balance after the last posting. The balance before the first
    posting counts as well.
    """
    balance = closing - sum((txn.amount for txn in postings), ZERO)
    lowest = balance
    for txn in postings:
        balance += txn.amount
        lowest = min(lowest, balance)
    return lowest


def maintenance_fee(account: Account, lowest: Decimal) -> Decimal:
    """Return the monthly maintenance fee of an account.

    Checking accounts pay MAINTENANCE_FEE unless their lowest balance of the month was
    FEE_WAIVER_BALANCE or more. Savings accounts never pay it.
    """
    if account.kind is not AccountKind.CHECKING or lowest >= FEE_WAIVER_BALANCE:
        return ZERO
    return MAINTENANCE_FEE


def excess_withdrawal_fee(
    account: Account, postings: Sequence[Transaction], year: int, month: int
) -> Decimal:
    """Return the charge for the month's savings withdrawals beyond the free ones.

    A savings account may make FREE_WITHDRAWALS withdrawals or outgoing transfers a
    month; each further one costs EXCESS_WITHDRAWAL_FEE. Postings outside the month
    are ignored. Checking accounts have no such limit.
    """
    first, last = month_range(year, month)
    fee = ZERO
    if account.kind is AccountKind.SAVINGS:
        used = 0
        for txn in postings:
            if first <= txn.posted_on <= last:
                if txn.kind in _DEBIT_KINDS:
                    used += 1
                    if used > FREE_WITHDRAWALS:
                        fee += EXCESS_WITHDRAWAL_FEE
    return fee


def monthly_fees(
    account: Account, postings: Sequence[Transaction], year: int, month: int
) -> list[tuple[Decimal, str]]:
    """Return the fees for a month as (amount, memo) pairs, leaving out fees of zero.

    ``postings`` are the month's postings and ``account.balance`` the balance at the
    end of the month, before any fee is taken.
    """
    fees = [
        (maintenance_fee(account, lowest_balance(account.balance, postings)), "maintenance fee"),
        (excess_withdrawal_fee(account, postings, year, month), "excess withdrawals"),
    ]
    return [(amount, memo) for amount, memo in fees if amount > ZERO]

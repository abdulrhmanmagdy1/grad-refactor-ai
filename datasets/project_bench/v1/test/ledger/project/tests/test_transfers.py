from datetime import date
from decimal import Decimal

import pytest

from ledger.accounts import (
    Account,
    AccountClosed,
    AccountKind,
    InsufficientFunds,
    LedgerError,
    UnknownAccount,
)
from ledger.money import AmountError
from ledger.store import LedgerStore
from ledger.transfers import close_account, deposit, transfer, withdraw


@pytest.fixture
def store():
    store = LedgerStore()
    store.add_account(
        Account(
            "CHK-1",
            "Ana Lima",
            AccountKind.CHECKING,
            date(2024, 1, 3),
            overdraft_limit=Decimal("200.00"),
        )
    )
    store.add_account(Account("SAV-1", "Ana Lima", AccountKind.SAVINGS, date(2024, 1, 3)))
    store.add_account(Account("CHK-2", "Ben Ode", AccountKind.CHECKING, date(2024, 2, 9)))
    yield store
    store.close()


def test_deposit_then_withdraw_updates_the_stored_balance(store):
    deposit(store, "CHK-1", "250.00", date(2024, 3, 1))
    withdraw(store, "CHK-1", "100.25", date(2024, 3, 2))
    assert store.get_account("CHK-1").balance == Decimal("149.75")


def test_savings_withdrawal_above_the_balance_is_refused(store):
    deposit(store, "SAV-1", "40.00", date(2024, 3, 1))
    with pytest.raises(InsufficientFunds):
        withdraw(store, "SAV-1", "40.01", date(2024, 3, 2))
    assert store.get_account("SAV-1").balance == Decimal("40.00")


def test_transfer_moves_money_and_records_both_sides(store):
    deposit(store, "CHK-1", "500.00", date(2024, 3, 1))
    out, into = transfer(store, "CHK-1", "SAV-1", "120.00", date(2024, 3, 4))
    assert out.amount == Decimal("-120.00")
    assert into.amount == Decimal("120.00")
    assert store.get_account("CHK-1").balance == Decimal("380.00")
    assert store.get_account("SAV-1").balance == Decimal("120.00")
    postings = store.transactions_for(["CHK-1", "SAV-1"], date(2024, 3, 1), date(2024, 3, 31))
    assert len(postings) == 3


def test_transfer_from_a_closed_account_is_refused(store):
    close_account(store, "CHK-2", date(2024, 3, 1))
    with pytest.raises(AccountClosed):
        transfer(store, "CHK-2", "SAV-1", "10.00", date(2024, 3, 2))


def test_transfer_to_the_same_account_is_refused(store):
    with pytest.raises(LedgerError):
        transfer(store, "CHK-1", "CHK-1", "10.00", date(2024, 3, 2))


def test_amounts_must_be_positive_money(store):
    with pytest.raises(AmountError):
        deposit(store, "CHK-1", "0", date(2024, 3, 1))
    with pytest.raises(AmountError):
        deposit(store, "CHK-1", "ten", date(2024, 3, 1))


def test_closing_pays_out_the_balance_and_blocks_deposits(store):
    deposit(store, "SAV-1", "75.50", date(2024, 3, 1))
    payout = close_account(store, "SAV-1", date(2024, 3, 9))
    assert payout is not None
    assert payout.amount == Decimal("-75.50")
    assert store.get_account("SAV-1").closed
    with pytest.raises(AccountClosed):
        deposit(store, "SAV-1", "1.00", date(2024, 3, 10))


def test_unknown_account_is_reported(store):
    with pytest.raises(UnknownAccount):
        deposit(store, "NOPE", "1.00", date(2024, 3, 1))


def test_accounts_are_found_by_owner(store):
    found = store.find_accounts_by_owner("Ana Lima")
    assert [account.account_id for account in found] == ["CHK-1", "SAV-1"]

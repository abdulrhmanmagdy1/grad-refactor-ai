import hashlib
from datetime import date
from decimal import Decimal

import pytest

from ledger.accounts import Account, AccountKind, InsufficientFunds, LedgerError, TxnKind
from ledger.interest import monthly_interest, rate_for_balance
from ledger.statements import build_statement, statement_fingerprint
from ledger.store import LedgerStore
from ledger.transfers import close_account, deposit, transfer, withdraw


@pytest.fixture
def store():
    store = LedgerStore()
    store.add_account(
        Account(
            "C-1",
            "alice",
            AccountKind.CHECKING,
            date(2024, 1, 2),
            overdraft_limit=Decimal("100.00"),
        )
    )
    store.add_account(Account("S-1", "alice", AccountKind.SAVINGS, date(2024, 1, 2)))
    store.add_account(Account("C-2", "bob", AccountKind.CHECKING, date(2024, 2, 1)))
    yield store
    store.close()


# --- seeded issues -------------------------------------------------------------


def test_B1_withdrawal_may_use_the_overdraft_limit(store):
    deposit(store, "C-1", "50.00", date(2024, 3, 1))
    withdraw(store, "C-1", "120.00", date(2024, 3, 2))
    assert store.get_account("C-1").balance == Decimal("-70.00")
    withdraw(store, "C-1", "30.00", date(2024, 3, 3))
    assert store.get_account("C-1").balance == Decimal("-100.00")


def test_B2_monthly_interest_rounds_half_up():
    assert monthly_interest(Decimal("1350.00"), Decimal("0.0100")) == Decimal("1.13")
    assert monthly_interest(Decimal("6100.00"), Decimal("0.0150")) == Decimal("7.63")


def test_B3_transfer_into_a_closed_account_is_refused(store):
    deposit(store, "C-1", "200.00", date(2024, 3, 1))
    close_account(store, "C-2", date(2024, 3, 2))
    with pytest.raises(LedgerError):
        transfer(store, "C-1", "C-2", "50.00", date(2024, 3, 3))
    assert store.get_account("C-1").balance == Decimal("200.00")
    assert store.get_account("C-2").balance == Decimal("0.00")


def test_S1_owner_search_does_not_run_text_as_sql(store):
    try:
        found = store.find_accounts_by_owner("nobody' OR '1'='1")
    except ValueError:
        return
    assert found == []


# --- behaviour that must keep working ------------------------------------------


def test_keep_withdrawal_past_the_overdraft_limit_is_refused(store):
    deposit(store, "C-1", "50.00", date(2024, 3, 1))
    with pytest.raises(InsufficientFunds):
        withdraw(store, "C-1", "150.01", date(2024, 3, 2))
    assert store.get_account("C-1").balance == Decimal("50.00")


def test_keep_withdrawal_within_the_balance(store):
    deposit(store, "S-1", "80.00", date(2024, 3, 1))
    txn = withdraw(store, "S-1", "80.00", date(2024, 3, 2))
    assert txn.amount == Decimal("-80.00")
    assert store.get_account("S-1").balance == Decimal("0.00")


def test_keep_transfer_may_use_the_overdraft_limit(store):
    transfer(store, "C-1", "S-1", "100.00", date(2024, 3, 1))
    assert store.get_account("C-1").balance == Decimal("-100.00")
    assert store.get_account("S-1").balance == Decimal("100.00")
    with pytest.raises(InsufficientFunds):
        transfer(store, "C-1", "S-1", "0.01", date(2024, 3, 2))


def test_keep_transfer_between_open_accounts_of_different_owners(store):
    deposit(store, "S-1", "60.00", date(2024, 3, 1))
    out, into = transfer(store, "S-1", "C-2", "60.00", date(2024, 3, 5))
    assert (out.kind, into.kind) == (TxnKind.TRANSFER_OUT, TxnKind.TRANSFER_IN)
    assert store.get_account("C-2").balance == Decimal("60.00")


def test_keep_interest_without_a_half_cent():
    assert monthly_interest(Decimal("1200.00"), Decimal("0.0100")) == Decimal("1.00")
    assert monthly_interest(Decimal("1234.56"), Decimal("0.0100")) == Decimal("1.03")
    assert monthly_interest(Decimal("-10.00"), Decimal("0.0100")) == Decimal("0")
    assert rate_for_balance(AccountKind.SAVINGS, Decimal("25000.00")) == Decimal("0.0200")


def test_keep_owner_search_matches_exact_names(store):
    assert [a.account_id for a in store.find_accounts_by_owner("alice")] == ["C-1", "S-1"]
    assert [a.account_id for a in store.find_accounts_by_owner("bob")] == ["C-2"]
    assert store.find_accounts_by_owner("carol") == []


def test_keep_postings_query_handles_several_accounts_and_quotes(store):
    store.add_account(Account("X'1", "dora", AccountKind.SAVINGS, date(2024, 1, 2)))
    deposit(store, "C-1", "10.00", date(2024, 2, 29))
    deposit(store, "C-1", "11.00", date(2024, 3, 1))
    deposit(store, "X'1", "12.00", date(2024, 3, 15))
    deposit(store, "S-1", "13.00", date(2024, 3, 31))
    deposit(store, "C-2", "14.00", date(2024, 3, 20))
    deposit(store, "S-1", "15.00", date(2024, 4, 1))
    found = store.transactions_for(["C-1", "S-1", "X'1"], date(2024, 3, 1), date(2024, 3, 31))
    assert [t.amount for t in found] == [Decimal("11.00"), Decimal("12.00"), Decimal("13.00")]
    assert store.transactions_for([], date(2024, 3, 1), date(2024, 3, 31)) == []


def test_keep_statement_fingerprint_matches_statements_already_sent():
    text = "alice - checking account C-1\nStatement 2024-03-01 to 2024-03-31"
    assert statement_fingerprint(text) == hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def test_keep_statement_includes_the_last_day_of_the_month(store):
    deposit(store, "C-2", "100.00", date(2024, 2, 29))
    deposit(store, "C-2", "40.00", date(2024, 3, 31))
    deposit(store, "C-2", "5.00", date(2024, 4, 1))
    statement = build_statement(store, "C-2", 2024, 3)
    assert statement.opening_balance == Decimal("100.00")
    assert statement.closing_balance == Decimal("140.00")
    assert [t.amount for t in statement.postings] == [Decimal("40.00")]


def test_keep_month_end_interest_and_fee_on_one_account(store):
    store.add_account(Account("S-2", "erin", AccountKind.SAVINGS, date(2024, 1, 2)))
    deposit(store, "S-2", "2400.00", date(2024, 5, 1))
    for day in range(2, 9):
        withdraw(store, "S-2", "1.00", date(2024, 5, day))
    posted = store.post_month_end("S-2", 2024, 5)
    assert [(t.kind, t.amount) for t in posted] == [
        (TxnKind.INTEREST, Decimal("1.99")),
        (TxnKind.FEE, Decimal("-2.00")),
    ]
    assert store.get_account("S-2").balance == Decimal("2392.99")

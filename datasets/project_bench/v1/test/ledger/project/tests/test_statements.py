from datetime import date
from decimal import Decimal

import pytest

from ledger.accounts import Account, AccountKind
from ledger.statements import build_statement, render_statement
from ledger.store import LedgerStore
from ledger.transfers import deposit, withdraw


@pytest.fixture
def store():
    store = LedgerStore()
    store.add_account(Account("CHK-7", "Eve Moss", AccountKind.CHECKING, date(2024, 1, 5)))
    deposit(store, "CHK-7", "100.00", date(2024, 2, 28))
    deposit(store, "CHK-7", "500.00", date(2024, 3, 1))
    withdraw(store, "CHK-7", "50.00", date(2024, 3, 31))
    deposit(store, "CHK-7", "20.00", date(2024, 4, 2))
    yield store
    store.close()


def test_statement_covers_the_whole_month(store):
    statement = build_statement(store, "CHK-7", 2024, 3)
    assert statement.first_day == date(2024, 3, 1)
    assert statement.last_day == date(2024, 3, 31)
    assert statement.opening_balance == Decimal("100.00")
    assert statement.closing_balance == Decimal("550.00")
    assert [t.amount for t in statement.postings] == [Decimal("500.00"), Decimal("-50.00")]
    assert statement.total_credits == Decimal("500.00")
    assert statement.total_debits == Decimal("50.00")


def test_rendered_statement_shows_running_balance_and_fingerprint(store):
    text = render_statement(build_statement(store, "CHK-7", 2024, 3))
    lines = text.splitlines()
    assert lines[0] == "Eve Moss - checking account CHK-7"
    assert "600.00" in lines[3]
    assert "550.00" in lines[4]
    assert lines[-1].startswith("Fingerprint ")
    assert len(lines[-1].split()[1]) == 12
    assert render_statement(build_statement(store, "CHK-7", 2024, 3)) == text

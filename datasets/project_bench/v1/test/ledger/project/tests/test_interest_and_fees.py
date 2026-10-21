from datetime import date
from decimal import Decimal

from ledger.accounts import Account, AccountKind, Transaction, TxnKind
from ledger.fees import excess_withdrawal_fee, lowest_balance, maintenance_fee
from ledger.interest import monthly_interest, projected_interest, rate_for_balance
from ledger.store import LedgerStore
from ledger.transfers import deposit, withdraw


def _account(kind: AccountKind, balance: str = "0.00") -> Account:
    return Account("A-1", "Cleo Park", kind, date(2023, 6, 1), balance=Decimal(balance))


def _debit(day: int, month: int = 5) -> Transaction:
    return Transaction("A-1", date(2024, month, day), TxnKind.WITHDRAWAL, Decimal("-10.00"))


def test_savings_rate_follows_the_tiers():
    assert rate_for_balance(AccountKind.SAVINGS, Decimal("4999.99")) == Decimal("0.0100")
    assert rate_for_balance(AccountKind.SAVINGS, Decimal("5000.00")) == Decimal("0.0150")
    assert rate_for_balance(AccountKind.SAVINGS, Decimal("30000.00")) == Decimal("0.0200")
    assert rate_for_balance(AccountKind.CHECKING, Decimal("30000.00")) == Decimal("0")
    assert rate_for_balance(AccountKind.SAVINGS, Decimal("-1.00")) == Decimal("0")


def test_monthly_interest_on_round_amounts():
    assert monthly_interest(Decimal("1200.00"), Decimal("0.0100")) == Decimal("1.00")
    assert monthly_interest(Decimal("6000.00"), Decimal("0.0150")) == Decimal("7.50")
    assert monthly_interest(Decimal("0.00"), Decimal("0.0100")) == Decimal("0")


def test_projected_interest_adds_each_month():
    assert projected_interest(AccountKind.SAVINGS, Decimal("1200.00"), 3) == Decimal("3.00")


def test_maintenance_fee_is_waived_from_the_threshold():
    checking = _account(AccountKind.CHECKING)
    assert maintenance_fee(checking, Decimal("1000.00")) == Decimal("0")
    assert maintenance_fee(checking, Decimal("999.99")) == Decimal("5.00")
    assert maintenance_fee(_account(AccountKind.SAVINGS), Decimal("10.00")) == Decimal("0")


def test_lowest_balance_counts_the_opening_balance():
    credit = Transaction("A-1", date(2024, 5, 2), TxnKind.DEPOSIT, Decimal("50.00"))
    debit = Transaction("A-1", date(2024, 5, 3), TxnKind.WITHDRAWAL, Decimal("-80.00"))
    assert lowest_balance(Decimal("100.00"), [credit, debit]) == Decimal("100.00")
    assert lowest_balance(Decimal("100.00"), [debit, credit]) == Decimal("50.00")


def test_only_savings_withdrawals_past_the_free_ones_cost_extra():
    postings = [_debit(day) for day in range(1, 9)] + [_debit(2, month=6)]
    savings = _account(AccountKind.SAVINGS)
    assert excess_withdrawal_fee(savings, postings, 2024, 5) == Decimal("4.00")
    assert excess_withdrawal_fee(_account(AccountKind.CHECKING), postings, 2024, 5) == Decimal("0")


def test_month_end_posts_interest_and_fees():
    store = LedgerStore()
    store.add_account(Account("SAV-9", "Dan Roy", AccountKind.SAVINGS, date(2024, 1, 1)))
    store.add_account(Account("CHK-9", "Dan Roy", AccountKind.CHECKING, date(2024, 1, 1)))
    deposit(store, "SAV-9", "1200.00", date(2024, 3, 1))
    deposit(store, "CHK-9", "400.00", date(2024, 3, 1))
    withdraw(store, "CHK-9", "100.00", date(2024, 3, 20))

    interest = store.post_month_end("SAV-9", 2024, 3)
    fees = store.post_month_end("CHK-9", 2024, 3)

    assert [(t.kind, t.amount) for t in interest] == [(TxnKind.INTEREST, Decimal("1.00"))]
    assert [(t.kind, t.amount) for t in fees] == [(TxnKind.FEE, Decimal("-5.00"))]
    assert fees[0].posted_on == date(2024, 3, 31)
    assert store.get_account("SAV-9").balance == Decimal("1201.00")
    assert store.get_account("CHK-9").balance == Decimal("295.00")
    store.close()

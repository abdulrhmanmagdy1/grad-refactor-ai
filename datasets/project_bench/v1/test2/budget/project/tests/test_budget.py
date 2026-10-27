from datetime import date
from decimal import Decimal

import pytest

from budget.budgets import MonthlyBudget, spent_in_month, track
from budget.ledger import InsufficientFundsError, Ledger
from budget.money import months_between, to_money
from budget.recurring import RecurringRule, monthly_commitment, occurrences, post_due
from budget.report import format_money, render_budgets, render_month
from budget.summary import income_and_spending, monthly_totals, spending_by_category

D = Decimal


def ledger() -> Ledger:
    book = Ledger()
    book.open_account("checking", D("1000"))
    book.open_account("card", allow_overdraft=True)
    return book


def test_money_rounding_and_months():
    assert to_money("2.345") == D("2.35")
    with pytest.raises(TypeError):
        to_money(0.1)
    assert months_between((2026, 11), (2027, 2)) == [(2026, 11), (2026, 12), (2027, 1), (2027, 2)]


def test_record_and_balance():
    book = ledger()
    book.record("checking", date(2026, 1, 5), D("-120.50"), "groceries", "market")
    book.record("checking", date(2026, 1, 9), D("2000"), "salary")
    assert book.balance("checking") == D("2879.50")
    with pytest.raises(InsufficientFundsError):
        book.record("checking", date(2026, 1, 10), D("-5000"), "rent")


def test_transfer_and_filtering():
    book = ledger()
    book.transfer("checking", "card", date(2026, 2, 1), D("300"))
    assert book.balance("card") == D("300.00")
    assert [t.memo for t in book.transactions(account="checking")] == ["to card"]
    assert len(book.transactions(start=date(2026, 2, 2))) == 0


def test_search_by_memo():
    book = ledger()
    book.record("card", date(2026, 1, 3), D("-12"), "dining", "Pizza place")
    book.record("card", date(2026, 1, 4), D("-40"), "fuel", "Gas station")
    assert [t.memo for t in book.search("pizza")] == ["Pizza place"]


def test_recurring_rent():
    rule = RecurringRule("checking", D("-700"), "rent", "rent", 1, date(2026, 1, 1))
    assert occurrences(rule, date(2026, 1, 1), date(2026, 3, 15)) == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
    book = Ledger()
    book.open_account("checking", D("5000"))
    assert len(post_due(book, [rule], date(2026, 1, 1), date(2026, 2, 28))) == 2
    assert book.balance("checking") == D("3600.00")
    assert monthly_commitment([rule], 2026, 4) == D("-700.00")


def test_budget_without_rollover():
    book = ledger()
    book.record("card", date(2026, 1, 3), D("-80"), "dining")
    book.record("card", date(2026, 1, 20), D("10"), "dining", "refund")
    assert spent_in_month(book.transactions(), "dining", 2026, 1) == D("70.00")
    statuses = track(MonthlyBudget("dining", D("100")), book.transactions(), (2026, 1), (2026, 2))
    assert [s.available for s in statuses] == [D("100.00"), D("100.00")]
    assert "dining" in render_budgets(statuses)


def test_summaries_and_report():
    book = ledger()
    book.record("card", date(2026, 3, 2), D("-75"), "groceries")
    book.record("card", date(2026, 3, 5), D("-25"), "dining")
    book.record("checking", date(2026, 3, 1), D("1500"), "salary")
    book.transfer("checking", "card", date(2026, 3, 10), D("100"))
    totals = spending_by_category(book.transactions(), date(2026, 3, 1), date(2026, 3, 31))
    assert [(t.category, t.share) for t in totals] == [("groceries", D("75.0")), ("dining", D("25.0"))]
    assert income_and_spending(book.transactions(), 2026, 3) == (D("1500.00"), D("100.00"))
    assert monthly_totals(book.transactions(), date(2026, 2, 1), date(2026, 3, 31))[(2026, 2)] == D("0.00")
    assert format_money(D("-1234.5")) == "-$1,234.50"
    assert "groceries" in render_month(book.transactions(), 2026, 3)

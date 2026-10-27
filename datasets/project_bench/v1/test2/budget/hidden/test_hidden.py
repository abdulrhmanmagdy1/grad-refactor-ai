from datetime import date
from decimal import Decimal

import pytest

from budget.budgets import MonthlyBudget, track
from budget.ledger import InsufficientFundsError, Ledger
from budget.models import Transaction
from budget.recurring import RecurringRule, occurrences, post_due
from budget.summary import monthly_average

D = Decimal


def expense(txn_id: int, day: date, amount: str, category: str = "dining") -> Transaction:
    return Transaction(txn_id, "card", day, D(amount), category)


def test_B1_average_counts_every_month_in_the_period():
    txns = [expense(1, date(2026, 1, 10), "-60"), expense(2, date(2026, 1, 20), "-30")]
    assert monthly_average(txns, "dining", date(2026, 1, 1), date(2026, 3, 31)) == D("30.00")


def test_keep_average_with_one_month_and_no_spending():
    txns = [expense(1, date(2026, 1, 10), "-60"), expense(3, date(2026, 1, 21), "-5", "fuel")]
    assert monthly_average(txns, "dining", date(2026, 1, 1), date(2026, 1, 31)) == D("60.00")
    assert monthly_average(txns, "rent", date(2026, 1, 1), date(2026, 2, 28)) == D("0.00")


def test_B2_rule_on_the_31st_falls_on_the_last_day_of_short_months():
    rule = RecurringRule("checking", D("-50"), "gym", "gym", 31, date(2026, 1, 1))
    assert occurrences(rule, date(2026, 1, 1), date(2026, 4, 30)) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]
    leap = RecurringRule("checking", D("-50"), "gym", "gym", 30, date(2028, 1, 1))
    assert occurrences(leap, date(2028, 2, 1), date(2028, 2, 29)) == [date(2028, 2, 29)]


def test_keep_occurrences_respect_rule_dates():
    rule = RecurringRule("checking", D("-50"), "gym", "gym", 15, date(2026, 2, 16), date(2026, 4, 15))
    assert occurrences(rule, date(2026, 1, 1), date(2026, 12, 31)) == [date(2026, 3, 15), date(2026, 4, 15)]


def test_B3_unspent_money_rolls_over_and_overspending_does_not():
    txns = [
        expense(1, date(2026, 1, 5), "-70"),
        expense(2, date(2026, 2, 5), "-200"),
    ]
    statuses = track(MonthlyBudget("dining", D("100"), rollover=True), txns, (2026, 1), (2026, 3))
    assert [s.available for s in statuses] == [D("100.00"), D("130.00"), D("100.00")]


def test_keep_budget_without_rollover_and_over_flag():
    txns = [expense(1, date(2026, 1, 5), "-100"), expense(2, date(2026, 2, 5), "-100.01")]
    statuses = track(MonthlyBudget("dining", D("100")), txns, (2026, 1), (2026, 2))
    assert [s.available for s in statuses] == [D("100.00"), D("100.00")]
    assert [s.over_budget for s in statuses] == [False, True]


def book() -> Ledger:
    ledger = Ledger()
    ledger.open_account("card", allow_overdraft=True)
    ledger.record("card", date(2026, 1, 3), D("-12"), "dining", "Joe's Diner")
    ledger.record("card", date(2026, 1, 4), D("-40"), "fuel", "Gas station")
    return ledger


def test_S1_search_text_is_not_part_of_the_sql():
    ledger = book()
    assert [t.memo for t in ledger.search("Joe's")] == ["Joe's Diner"]
    assert ledger.search("zzz' OR 1=1 OR memo LIKE '") == []
    assert len(ledger.transactions()) == 2


def test_keep_filtered_queries_use_parameters():
    ledger = book()
    assert [t.memo for t in ledger.transactions(account="card", start=date(2026, 1, 4))] == ["Gas station"]
    assert ledger.transactions(account="x' OR '1'='1") == []
    assert [t.memo for t in ledger.search("Gas")] == ["Gas station"]


def test_keep_failed_recurring_post_is_reraised():
    ledger = Ledger()
    ledger.open_account("checking", D("100"))
    rule = RecurringRule("checking", D("-80"), "rent", "rent", 1, date(2026, 1, 1))
    with pytest.raises(InsufficientFundsError):
        post_due(ledger, [rule], date(2026, 1, 1), date(2026, 2, 28))
    assert ledger.balance("checking") == D("20.00")

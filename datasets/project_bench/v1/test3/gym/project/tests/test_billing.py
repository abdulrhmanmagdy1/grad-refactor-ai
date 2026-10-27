from datetime import date
from decimal import Decimal

import pytest

from gym.billing import Ledger, bill_plan_fees, prorated_fee
from gym.memberships import MembershipBook
from gym.models import Member, Plan

PLAN = Plan("Y1", "Yearly", Decimal("30.00"), duration_days=365)


def test_charge_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Ledger().charge("m1", Decimal("0"), "nothing")


def test_close_month_issues_one_invoice_per_member() -> None:
    ledger = Ledger()
    ledger.charge("m2", Decimal("12.50"), "towel")
    ledger.charge("m1", Decimal("5.00"), "locker")
    ledger.charge("m1", Decimal("2.50"), "water")
    invoices = ledger.close_month(2026, 3)
    assert [(i.member_id, i.month, i.total) for i in invoices] == [
        ("m1", "2026-03", Decimal("7.50")),
        ("m2", "2026-03", Decimal("12.50")),
    ]


def test_prorated_fee_scales_with_covered_days() -> None:
    book = MembershipBook(Ledger())
    book.register(Member("m1", "Sara", "sara@example.com"))
    membership = book.sell("m1", PLAN, date(2026, 4, 16))
    assert prorated_fee(membership, 2026, 4) == Decimal("15.00")
    assert prorated_fee(membership, 2026, 5) == Decimal("30.00")
    assert prorated_fee(membership, 2026, 3) == Decimal("0.00")


def test_bill_plan_fees_skips_unused_months() -> None:
    ledger = Ledger()
    book = MembershipBook(ledger)
    book.register(Member("m1", "Sara", "sara@example.com"))
    book.register(Member("m2", "Omar", "omar@example.com"))
    book.sell("m1", PLAN, date(2026, 4, 1))
    book.sell("m2", PLAN, date(2026, 5, 1))
    charged = bill_plan_fees(book, ledger, 2026, 4)
    assert [(c.member_id, c.amount) for c in charged] == [("m1", Decimal("30.00"))]

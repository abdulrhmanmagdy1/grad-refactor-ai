from datetime import date
from decimal import Decimal

import pytest

from gym.billing import Ledger
from gym.memberships import MembershipBook, MembershipError, active_days
from gym.models import Member, Plan

MONTHLY = Plan("M1", "Monthly", Decimal("31.00"), duration_days=30, max_freeze_days=14)


@pytest.fixture
def book() -> MembershipBook:
    book = MembershipBook(Ledger())
    book.register(Member("m1", "Sara", "sara@example.com"))
    return book


def test_register_rejects_duplicate_ids(book: MembershipBook) -> None:
    with pytest.raises(MembershipError):
        book.register(Member("m1", "Other", "other@example.com"))


def test_sell_counts_the_first_day(book: MembershipBook) -> None:
    membership = book.sell("m1", MONTHLY, date(2026, 3, 1))
    assert membership.expires == date(2026, 3, 30)
    assert membership.covers(date(2026, 3, 30))
    assert not membership.covers(date(2026, 3, 31))


def test_sell_requires_a_registered_member(book: MembershipBook) -> None:
    with pytest.raises(MembershipError):
        book.sell("nobody", MONTHLY, date(2026, 3, 1))


def test_freeze_cannot_end_before_it_starts(book: MembershipBook) -> None:
    book.sell("m1", MONTHLY, date(2026, 3, 1))
    with pytest.raises(MembershipError):
        book.freeze("m1", date(2026, 3, 10), date(2026, 3, 9))


def test_cancel_refunds_the_rest_of_the_month(book: MembershipBook) -> None:
    book.sell("m1", Plan("Q1", "Quarter", Decimal("31.00"), duration_days=90), date(2026, 3, 1))
    refund = book.cancel("m1", date(2026, 3, 21))
    assert refund == Decimal("10.00")
    assert book.get("m1").expires == date(2026, 3, 21)


def test_active_days_counts_the_covered_days(book: MembershipBook) -> None:
    membership = book.sell("m1", MONTHLY, date(2026, 3, 1))
    assert active_days(membership, 2026, 3) == 30
    assert active_days(membership, 2026, 4) == 0

from datetime import date, datetime
from decimal import Decimal

import pytest

from gym.billing import Ledger
from gym.checkins import CheckInDesk, CheckInError
from gym.memberships import MembershipBook
from gym.models import Member, Plan

PLAN = Plan("M1", "Monthly", Decimal("30.00"), duration_days=30)


@pytest.fixture
def desk() -> CheckInDesk:
    book = MembershipBook(Ledger())
    book.register(Member("m1", "Sara", "sara@example.com"))
    book.register(Member("m2", "Omar", "omar@example.com"))
    book.sell("m1", PLAN, date(2026, 3, 1))
    return CheckInDesk(book)


def test_member_with_token_is_admitted_once_a_day(desk: CheckInDesk) -> None:
    token = desk.issue_token("m1")
    visit = desk.check_in(token, datetime(2026, 3, 5, 8, 0))
    assert visit.member_id == "m1"
    with pytest.raises(CheckInError):
        desk.check_in(token, datetime(2026, 3, 5, 19, 0))
    desk.check_in(token, datetime(2026, 3, 6, 8, 0))
    assert len(desk.visits_in_month(2026, 3)) == 2


def test_new_token_replaces_the_old_one(desk: CheckInDesk) -> None:
    old = desk.issue_token("m1")
    new = desk.issue_token("m1")
    with pytest.raises(CheckInError):
        desk.check_in(old, datetime(2026, 3, 5, 8, 0))
    assert desk.check_in(new, datetime(2026, 3, 5, 8, 0)).member_id == "m1"


def test_member_without_membership_is_refused(desk: CheckInDesk) -> None:
    token = desk.issue_token("m2")
    with pytest.raises(CheckInError):
        desk.check_in(token, datetime(2026, 3, 5, 8, 0))


def test_expired_membership_is_refused(desk: CheckInDesk) -> None:
    token = desk.issue_token("m1")
    with pytest.raises(CheckInError):
        desk.check_in(token, datetime(2026, 4, 2, 8, 0))


def test_unknown_member_gets_no_token(desk: CheckInDesk) -> None:
    with pytest.raises(CheckInError):
        desk.issue_token("ghost")

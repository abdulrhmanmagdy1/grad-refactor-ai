import random
from datetime import date, datetime
from decimal import Decimal

import pytest

from gym.billing import Ledger, prorated_fee
from gym.checkins import CheckInDesk, CheckInError
from gym.classes import GymClass, Schedule
from gym.memberships import MembershipBook, MembershipError
from gym.models import Member, Plan

PLAN = Plan("M1", "Monthly", Decimal("30.00"), duration_days=30, max_freeze_days=10)


def make_book(*member_ids: str) -> MembershipBook:
    book = MembershipBook(Ledger())
    for member_id in member_ids:
        book.register(Member(member_id, member_id.title(), f"{member_id}@example.com"))
    return book


def test_B1_freeze_counts_both_first_and_last_day() -> None:
    book = make_book("m1")
    book.sell("m1", PLAN, date(2026, 3, 1))
    membership = book.freeze("m1", date(2026, 3, 10), date(2026, 3, 16))
    assert membership.frozen_days == 7
    assert membership.expires == date(2026, 4, 6)
    assert membership.covers(date(2026, 4, 6))


def test_B1_one_day_freeze_moves_expiry_by_one_day() -> None:
    book = make_book("m1")
    book.sell("m1", PLAN, date(2026, 3, 1))
    membership = book.freeze("m1", date(2026, 3, 10), date(2026, 3, 10))
    assert membership.frozen_days == 1
    assert membership.expires == date(2026, 3, 31)


def test_B1_freeze_allowance_counts_inclusive_days() -> None:
    book = make_book("m1")
    book.sell("m1", PLAN, date(2026, 3, 1))
    with pytest.raises(MembershipError):
        book.freeze("m1", date(2026, 3, 10), date(2026, 3, 20))


def test_B2_longest_waiting_member_gets_the_place() -> None:
    spin = GymClass("spin-1", "Spin", datetime(2026, 3, 2, 18, 0), 1)
    for member_id in ["a", "b", "c", "d"]:
        spin.book(member_id)
    assert spin.cancel("a") == "b"
    assert spin.booked == ["b"]
    assert spin.waitlist == ["c", "d"]
    assert spin.cancel("b") == "c"
    assert spin.waitlist == ["d"]


def test_B3_closed_charges_are_not_billed_again() -> None:
    ledger = Ledger()
    ledger.charge("m1", Decimal("30.00"), "plan fee 2026-03")
    ledger.close_month(2026, 3)
    ledger.charge("m1", Decimal("5.00"), "freeze")
    april = ledger.close_month(2026, 4)
    assert [(i.member_id, i.total) for i in april] == [("m1", Decimal("5.00"))]
    assert ledger.close_month(2026, 5) == []
    assert len(ledger.invoices) == 2


def test_S1_tokens_do_not_follow_the_random_module_seed() -> None:
    book = make_book("m1", "m2")
    book.sell("m1", PLAN, date(2026, 3, 1))
    book.sell("m2", PLAN, date(2026, 3, 1))
    desk = CheckInDesk(book)
    random.seed(1234)
    first = desk.issue_token("m1")
    random.seed(1234)
    second = desk.issue_token("m2")
    assert first != second
    assert desk.check_in(first, datetime(2026, 3, 3, 8, 0)).member_id == "m1"
    assert desk.check_in(second, datetime(2026, 3, 3, 8, 5)).member_id == "m2"


def test_keep_tokens_are_unique_and_admit_their_member() -> None:
    book = make_book("m1", "m2")
    book.sell("m1", PLAN, date(2026, 3, 1))
    desk = CheckInDesk(book)
    token = desk.issue_token("m1")
    assert isinstance(token, str) and len(token) >= 8
    assert desk.check_in(token, datetime(2026, 3, 3, 8, 0)).member_id == "m1"
    with pytest.raises(CheckInError):
        desk.check_in(token + "X", datetime(2026, 3, 4, 8, 0))


def test_keep_drop_lapsed_removes_every_lapsed_member() -> None:
    yoga = GymClass("yoga-1", "Yoga", datetime(2026, 3, 2, 18, 0), 1)
    for member_id in ["a", "b", "c", "d", "e"]:
        yoga.book(member_id)
    removed = yoga.drop_lapsed(lambda member_id: member_id in {"a", "e"})
    assert removed == ["b", "c", "d"]
    assert yoga.waitlist == ["e"]
    assert yoga.booked == ["a"]


def test_keep_version_tag_is_stable_and_tracks_moves() -> None:
    first, second = Schedule(), Schedule()
    for schedule in (first, second):
        schedule.add(GymClass("hiit-1", "HIIT", datetime(2026, 3, 4, 18, 0), 8))
    assert first.version_tag() == second.version_tag()
    second.get("hiit-1").starts_at = datetime(2026, 3, 4, 19, 0)
    assert first.version_tag() != second.version_tag()


def test_keep_waitlisted_member_leaving_promotes_nobody() -> None:
    spin = GymClass("spin-1", "Spin", datetime(2026, 3, 2, 18, 0), 1)
    for member_id in ["a", "b", "c"]:
        spin.book(member_id)
    assert spin.cancel("c") is None
    assert spin.waitlist == ["b"]


def test_keep_freeze_days_are_not_covered_and_fee_is_charged() -> None:
    book = make_book("m1")
    book.sell("m1", PLAN, date(2026, 3, 1))
    membership = book.freeze("m1", date(2026, 3, 10), date(2026, 3, 12))
    assert not membership.covers(date(2026, 3, 11))
    assert membership.covers(date(2026, 3, 13))
    assert [c.amount for c in book.ledger.pending["m1"]] == [Decimal("5.00")]


def test_keep_cancel_refund_and_prorated_fee() -> None:
    book = make_book("m1")
    membership = book.sell("m1", Plan("Y", "Year", Decimal("31.00"), 365), date(2026, 3, 1))
    assert prorated_fee(membership, 2026, 3) == Decimal("31.00")
    assert book.cancel("m1", date(2026, 3, 21)) == Decimal("10.00")
    assert prorated_fee(membership, 2026, 3) == Decimal("21.00")

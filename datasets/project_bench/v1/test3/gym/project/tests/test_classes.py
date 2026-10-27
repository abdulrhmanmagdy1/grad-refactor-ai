from datetime import datetime

import pytest

from gym.classes import BookingError, GymClass, Schedule


def make_class(class_id: str = "yoga-1", capacity: int = 2) -> GymClass:
    return GymClass(class_id, "Yoga", datetime(2026, 3, 2, 18, 0), capacity)


def test_booking_fills_then_waitlists() -> None:
    yoga = make_class()
    assert yoga.book("a") == "booked"
    assert yoga.book("b") == "booked"
    assert yoga.is_full
    assert yoga.book("c") == "waitlisted"
    assert yoga.waitlist == ["c"]


def test_double_booking_is_rejected() -> None:
    yoga = make_class()
    yoga.book("a")
    with pytest.raises(BookingError):
        yoga.book("a")


def test_leaving_the_waitlist_promotes_nobody() -> None:
    yoga = make_class(capacity=1)
    yoga.book("a")
    yoga.book("b")
    assert yoga.cancel("b") is None
    assert yoga.booked == ["a"]
    assert yoga.waitlist == []


def test_cancel_without_a_waitlist_frees_the_place() -> None:
    yoga = make_class()
    yoga.book("a")
    assert yoga.cancel("a") is None
    assert not yoga.booked


def test_drop_lapsed_keeps_active_members() -> None:
    yoga = make_class(capacity=1)
    for member_id in ["a", "b", "c", "d"]:
        yoga.book(member_id)
    removed = yoga.drop_lapsed(lambda member_id: member_id == "c")
    assert removed == ["b", "d"]
    assert yoga.waitlist == ["c"]


def test_schedule_lists_a_month_in_order() -> None:
    schedule = Schedule()
    late = GymClass("spin-2", "Spin", datetime(2026, 3, 2, 19, 0), 10)
    early = GymClass("spin-1", "Spin", datetime(2026, 3, 2, 7, 0), 10)
    schedule.add(late)
    schedule.add(early)
    schedule.add(GymClass("spin-0", "Spin", datetime(2026, 4, 1, 7, 0), 10))
    assert schedule.in_month(2026, 3) == [early, late]
    with pytest.raises(BookingError):
        schedule.add(GymClass("spin-3", "Spin", datetime(2026, 3, 3, 7, 0), 0))


def test_version_tag_follows_the_timetable_not_bookings() -> None:
    schedule = Schedule()
    schedule.add(make_class())
    before = schedule.version_tag()
    schedule.get("yoga-1").book("a")
    assert schedule.version_tag() == before
    schedule.add(make_class("yoga-2"))
    assert schedule.version_tag() != before

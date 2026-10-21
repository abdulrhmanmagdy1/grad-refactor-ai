from datetime import date, datetime, time

import pytest

from scheduler.bookings import Calendar, Conflict, Status
from scheduler.recurrence import Frequency, Recurrence
from scheduler.timeutil import Interval

DAY = date(2024, 5, 14)


def span(start: str, end: str, day: date = DAY) -> Interval:
    return Interval(
        datetime.combine(day, time.fromisoformat(start)),
        datetime.combine(day, time.fromisoformat(end)),
    )


def test_interval_must_end_after_it_starts():
    with pytest.raises(ValueError):
        span("10:00", "10:00")
    assert span("09:00", "10:30").duration.total_seconds() == 5400


def test_overlap_is_symmetric():
    long_meeting = span("09:00", "12:00")
    inside = span("10:00", "10:30")
    later = span("13:00", "14:00")
    assert long_meeting.overlaps(inside) and inside.overlaps(long_meeting)
    assert not long_meeting.overlaps(later) and not later.overlaps(long_meeting)


def test_booking_an_overlapping_time_raises_conflict():
    calendar = Calendar()
    first = calendar.book("atlas", "ana", "Planning", span("09:00", "10:00"))
    with pytest.raises(Conflict) as caught:
        calendar.book("atlas", "ben", "Review", span("09:30", "10:30"))
    assert caught.value.clashes == [first]
    calendar.book("borneo", "ben", "Review", span("09:30", "10:30"))


def test_bookings_must_fit_office_hours_and_quarter_hours():
    calendar = Calendar()
    with pytest.raises(ValueError):
        calendar.book("atlas", "ana", "Early", span("07:30", "08:30"))
    with pytest.raises(ValueError):
        calendar.book("atlas", "ana", "Late", span("17:30", "18:30"))
    with pytest.raises(ValueError):
        calendar.book("atlas", "ana", "Odd", span("09:10", "10:00"))


def test_holidays_close_the_office():
    christmas = date(2024, 12, 25)
    calendar = Calendar()
    calendar.add_holiday(christmas)
    assert calendar.is_holiday(christmas)
    with pytest.raises(ValueError):
        calendar.book("atlas", "ana", "Party", span("15:00", "16:00", christmas))


def test_cancelling_frees_the_room():
    calendar = Calendar()
    booking = calendar.book("atlas", "ana", "Planning", span("11:00", "12:00"))
    assert calendar.cancel(booking.booking_id).status is Status.CANCELLED
    calendar.book("atlas", "ben", "Retro", span("11:00", "12:00"))
    assert [b.title for b in calendar.bookings_on(DAY, "atlas")] == ["Retro"]


def test_rescheduling_ignores_the_old_time_of_the_same_booking():
    calendar = Calendar()
    booking = calendar.book("atlas", "ana", "Planning", span("09:00", "10:00"))
    moved = calendar.reschedule(booking.booking_id, span("09:30", "10:30"))
    assert moved.interval == span("09:30", "10:30")
    assert calendar.get(booking.booking_id) == moved


def test_series_is_all_or_nothing():
    calendar = Calendar()
    calendar.book("atlas", "ben", "Workshop", span("09:00", "11:00", date(2024, 5, 16)))
    with pytest.raises(Conflict):
        calendar.book_series(
            "atlas",
            "ana",
            "Stand-up",
            span("10:00", "10:30", date(2024, 5, 14)),
            Recurrence(Frequency.DAILY, count=3),
        )
    assert calendar.bookings_on(date(2024, 5, 14)) == []
    assert calendar.bookings_on(date(2024, 5, 15)) == []


def test_purge_forgets_old_cancelled_bookings():
    calendar = Calendar()
    kept = calendar.book("atlas", "ana", "Planning", span("09:00", "09:30"))
    dropped = calendar.book("atlas", "ana", "Review", span("11:00", "11:30"))
    calendar.cancel(dropped.booking_id)
    assert calendar.purge_cancelled(datetime(2024, 5, 15)) == 1
    assert calendar.get(kept.booking_id) == kept
    with pytest.raises(KeyError):
        calendar.get(dropped.booking_id)

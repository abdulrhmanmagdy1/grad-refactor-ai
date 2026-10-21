import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from scheduler.bookings import Calendar, Conflict
from scheduler.export import export_room_calendar
from scheduler.finder import find_room, free_slots
from scheduler.recurrence import Frequency, Recurrence, occurrences
from scheduler.reminders import send_due
from scheduler.rooms import Room, RoomDirectory
from scheduler.timeutil import Interval


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))


def span(day: date, start: tuple[int, int], end: tuple[int, int]) -> Interval:
    return Interval(at(day, *start), at(day, *end))


# --- seeded issues -------------------------------------------------------------


def test_B1_back_to_back_meetings_do_not_conflict():
    day = date(2031, 3, 4)
    first = span(day, (9, 0), (10, 0))
    second = span(day, (10, 0), (11, 0))
    assert not first.overlaps(second)
    assert not second.overlaps(first)
    calendar = Calendar()
    calendar.book("r1", "ann", "Planning", first)
    calendar.book("r1", "bob", "Review", second)
    assert [b.title for b in calendar.bookings_on(day, "r1")] == ["Planning", "Review"]


def test_B2_holidays_belong_to_one_calendar():
    holiday = date(2031, 1, 6)
    first = Calendar()
    first.add_holiday(holiday)
    second = Calendar()
    assert not second.is_holiday(holiday)
    booking = second.book("r1", "ann", "Kick-off", span(holiday, (9, 0), (10, 0)))
    assert booking.room_id == "r1"
    with pytest.raises(ValueError):
        first.book("r1", "ann", "Kick-off", span(holiday, (9, 0), (10, 0)))


def test_B3_recurring_series_keeps_organizer_and_title():
    monday = date(2031, 3, 10)
    calendar = Calendar()
    series = calendar.book_series(
        "r2",
        "ann",
        "Stand-up",
        span(monday, (9, 0), (9, 15)),
        Recurrence(Frequency.DAILY, count=3),
    )
    assert [(b.organizer, b.title) for b in series] == [("ann", "Stand-up")] * 3
    assert [b.interval.start.day for b in series] == [10, 11, 12]


def test_S1_export_stays_inside_the_export_folder(tmp_path):
    calendar = Calendar()
    calendar.book("r1", "ann", "Planning", span(date(2031, 4, 1), (9, 0), (10, 0)))
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    room = Room("r1", "Atlas", 8)
    try:
        written = export_room_calendar(calendar, room, export_dir, "../escaped")
    except (ValueError, PermissionError):
        written = None
    assert not (tmp_path / "escaped.ics").exists()
    if written is not None:
        assert export_dir.resolve() in Path(written).resolve().parents


# --- behaviour that must keep working ------------------------------------------


def test_keep_overlapping_meetings_still_conflict():
    day = date(2031, 3, 5)
    calendar = Calendar()
    calendar.book("r1", "ann", "Planning", span(day, (9, 0), (10, 0)))
    for clash in (
        span(day, (9, 45), (10, 30)),
        span(day, (8, 30), (9, 15)),
        span(day, (8, 0), (11, 0)),
        span(day, (9, 15), (9, 30)),
    ):
        with pytest.raises(Conflict):
            calendar.book("r1", "bob", "Clash", clash)
    assert span(day, (9, 0), (10, 0)).overlaps(span(day, (9, 59), (10, 0)))


def test_keep_holidays_given_to_a_calendar_close_it():
    holiday = date(2031, 5, 1)
    calendar = Calendar({holiday})
    assert calendar.is_holiday(holiday)
    with pytest.raises(ValueError):
        calendar.book("r1", "ann", "Planning", span(holiday, (9, 0), (10, 0)))
    calendar.book("r1", "ann", "Planning", span(date(2031, 5, 2), (9, 0), (10, 0)))


def test_keep_series_skips_holidays_and_weekends():
    calendar = Calendar()
    calendar.add_holiday(date(2031, 3, 18))
    series = calendar.book_series(
        "r3",
        "cy",
        "Sync",
        span(date(2031, 3, 14), (16, 0), (16, 30)),
        Recurrence(Frequency.DAILY, count=4),
    )
    assert [b.interval.start.date() for b in series] == [
        date(2031, 3, 14),
        date(2031, 3, 17),
        date(2031, 3, 19),
    ]


def test_keep_purge_removes_every_old_cancelled_booking():
    day = date(2031, 6, 3)
    calendar = Calendar()
    made = [
        calendar.book("r1", "ann", f"Meeting {hour}", span(day, (hour, 0), (hour, 30)))
        for hour in (9, 10, 11, 12)
    ]
    for booking in made[:3]:
        calendar.cancel(booking.booking_id)
    assert calendar.purge_cancelled(at(day, 17)) == 3
    assert calendar.get(made[3].booking_id) == made[3]
    for booking in made[:3]:
        with pytest.raises(KeyError):
            calendar.get(booking.booking_id)
    assert calendar.purge_cancelled(at(day, 17)) == 0


def test_keep_failed_notifier_is_logged_raised_and_retried(caplog):
    day = date(2031, 6, 4)
    calendar = Calendar()
    first = calendar.book("r1", "ann", "Planning", span(day, (9, 0), (10, 0)))
    second = calendar.book("r2", "bob", "Review", span(day, (9, 0), (10, 0)))
    delivered = []

    def flaky(recipient: str, text: str) -> None:
        if recipient == "bob":
            raise RuntimeError("mail server down")
        delivered.append(recipient)

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        send_due(calendar, at(day, 8, 55), flaky)
    assert delivered == ["ann"]
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors
    assert str(second.booking_id) in errors[-1].getMessage()
    retried = send_due(calendar, at(day, 8, 56), lambda *message: delivered.append(message[0]))
    assert [r.booking_id for r in retried] == [second.booking_id]
    assert first.booking_id != second.booking_id


def test_keep_monthly_series_and_until():
    starts = occurrences(datetime(2031, 1, 31, 9), Recurrence(Frequency.MONTHLY, count=3))
    assert [s.date() for s in starts] == [date(2031, 1, 31), date(2031, 3, 31), date(2031, 5, 31)]
    weekly = occurrences(
        datetime(2031, 3, 3, 9), Recurrence(Frequency.WEEKLY, until=date(2031, 3, 17))
    )
    assert [s.day for s in weekly] == [3, 10, 17]


def test_keep_free_slots_and_rooms_avoid_booked_time():
    day = date(2031, 6, 10)
    calendar = Calendar()
    calendar.book("small", "ann", "Planning", span(day, (10, 0), (11, 0)))
    starts = [s.start for s in free_slots(calendar, "small", day, timedelta(hours=1))]
    assert at(day, 12) in starts
    assert not [s for s in starts if at(day, 9, 15) <= s <= at(day, 10, 45)]
    directory = RoomDirectory([Room("big", "Big", 10), Room("small", "Small", 4)])
    room = find_room(directory, calendar, span(day, (10, 15), (10, 45)), 3)
    assert room is not None
    assert room.room_id == "big"


def test_keep_export_writes_the_named_file(tmp_path):
    calendar = Calendar()
    calendar.book("r1", "ann", "Planning", span(date(2031, 4, 2), (9, 0), (10, 0)))
    path = export_room_calendar(calendar, Room("r1", "Atlas", 8), tmp_path, "atlas-april")
    assert Path(path).resolve() == (tmp_path / "atlas-april.ics").resolve()
    text = Path(path).read_bytes().decode("utf-8")
    assert "SUMMARY:Planning\r\n" in text
    assert "LOCATION:Atlas\r\n" in text

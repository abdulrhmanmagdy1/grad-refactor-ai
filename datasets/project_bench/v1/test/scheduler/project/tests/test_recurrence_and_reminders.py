from datetime import date, datetime

import pytest

from scheduler.bookings import Calendar
from scheduler.recurrence import Frequency, Recurrence, occurrences
from scheduler.reminders import send_due
from scheduler.timeutil import Interval


class Outbox:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def __call__(self, recipient: str, text: str) -> None:
        self.messages.append((recipient, text))


def test_daily_series_skips_weekends():
    friday = datetime(2024, 5, 17, 9, 0)
    starts = occurrences(friday, Recurrence(Frequency.DAILY, count=3))
    assert [s.date() for s in starts] == [date(2024, 5, 17), date(2024, 5, 20), date(2024, 5, 21)]


def test_weekly_series_with_an_interval_and_an_end_date():
    first = datetime(2024, 5, 6, 14, 0)
    starts = occurrences(first, Recurrence(Frequency.WEEKLY, interval=2, until=date(2024, 6, 3)))
    assert [s.day for s in starts] == [6, 20, 3]


def test_monthly_series_on_the_31st_skips_short_months():
    first = datetime(2024, 1, 31, 9, 0)
    starts = occurrences(first, Recurrence(Frequency.MONTHLY, count=3))
    assert [s.month for s in starts] == [1, 3, 5]


def test_recurrence_needs_an_end():
    with pytest.raises(ValueError):
        Recurrence(Frequency.WEEKLY)
    with pytest.raises(ValueError):
        Recurrence(Frequency.WEEKLY, interval=0, count=2)


def test_due_reminders_are_sent_once():
    calendar = Calendar()
    calendar.book(
        "atlas", "ana", "Planning", Interval(datetime(2024, 5, 14, 9), datetime(2024, 5, 14, 10))
    )
    calendar.book(
        "atlas", "ben", "Review", Interval(datetime(2024, 5, 14, 14), datetime(2024, 5, 14, 15))
    )
    outbox = Outbox()

    sent = send_due(calendar, datetime(2024, 5, 14, 8, 55), outbox)

    assert [r.recipient for r in sent] == ["ana"]
    assert outbox.messages == [("ana", "Planning in room atlas at 09:00 on 2024-05-14")]
    assert send_due(calendar, datetime(2024, 5, 14, 8, 58), outbox) == []


def test_cancelled_bookings_send_no_reminder():
    calendar = Calendar()
    booking = calendar.book(
        "atlas", "ana", "Planning", Interval(datetime(2024, 5, 21, 9), datetime(2024, 5, 21, 10))
    )
    calendar.cancel(booking.booking_id)
    assert send_due(calendar, datetime(2024, 5, 21, 9, 0), Outbox()) == []

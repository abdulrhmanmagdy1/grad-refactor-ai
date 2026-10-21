"""Room bookings: conflict detection, office hours, holidays and recurring series."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from enum import StrEnum

from scheduler import reminders
from scheduler.recurrence import Recurrence, occurrences
from scheduler.timeutil import Interval


class Status(StrEnum):
    """Whether a booking still holds its room."""

    ACTIVE = "active"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Booking:
    """One meeting in one room."""

    booking_id: int
    room_id: str
    organizer: str
    title: str
    interval: Interval
    status: Status = Status.ACTIVE


class Conflict(Exception):
    """Raised when a room is already booked for part of the requested time."""

    def __init__(self, clashes: list[Booking]) -> None:
        super().__init__("room taken by " + ", ".join(f"#{b.booking_id}" for b in clashes))
        self.clashes = clashes


def _check_office_hours(interval: Interval) -> None:
    """Raise ValueError unless the interval fits in one office day, on quarter hours."""
    start, end = interval.start, interval.end
    if start.date() != end.date():
        raise ValueError("a booking must start and end on the same day")
    if start.time() < time(8, 0) or end.time() > time(18, 0):
        raise ValueError("bookings must lie between 08:00 and 18:00")
    if start.minute % 15 or end.minute % 15:
        raise ValueError("bookings start and end on a quarter hour")


class Calendar:
    """Every booking of the office, with the reminders that go with them."""

    def __init__(self, holidays: set[date] = set()) -> None:
        self._holidays = holidays
        self._bookings: dict[int, Booking] = {}
        self._reminders: list[reminders.Reminder] = []
        self._ids = itertools.count(1)

    def add_holiday(self, day: date) -> None:
        """Close the office on ``day``: nothing may be booked on it any more."""
        self._holidays.add(day)

    def is_holiday(self, day: date) -> bool:
        """Return True when the office is closed on ``day``."""
        return day in self._holidays

    def get(self, booking_id: int) -> Booking:
        """Return a booking by id; raises KeyError when there is none."""
        return self._bookings[booking_id]

    def conflicts(
        self, room_id: str, interval: Interval, ignore: int | None = None
    ) -> list[Booking]:
        """Return the active bookings of the room that overlap ``interval``.

        ``ignore`` leaves one booking out, so that a moved booking does not clash with
        its own old time.
        """
        return [
            booking
            for booking in self._bookings.values()
            if booking.room_id == room_id
            and booking.status is Status.ACTIVE
            and booking.booking_id != ignore
            and booking.interval.overlaps(interval)
        ]

    def _check_bookable(self, room_id: str, interval: Interval, ignore: int | None = None) -> None:
        _check_office_hours(interval)
        if self.is_holiday(interval.start.date()):
            raise ValueError(f"the office is closed on {interval.start.date()}")
        clashes = self.conflicts(room_id, interval, ignore)
        if clashes:
            raise Conflict(clashes)

    def book(self, room_id: str, organizer: str, title: str, interval: Interval) -> Booking:
        """Book a room for one meeting and schedule its reminder.

        Raises ValueError when the time is outside office hours or on a holiday, and
        Conflict when the room is already taken for part of it.
        """
        self._check_bookable(room_id, interval)
        booking = Booking(next(self._ids), room_id, organizer, title, interval)
        self._bookings[booking.booking_id] = booking
        self._reminders.extend(reminders.reminders_for(booking))
        return booking

    def book_series(
        self, room_id: str, organizer: str, title: str, first: Interval, rule: Recurrence
    ) -> list[Booking]:
        """Book every meeting of a recurring series, or none of them.

        The meetings start at the times ``rule`` gives from ``first`` and last as long
        as ``first``. Meetings that would fall on a holiday are left out. If any other
        meeting cannot be booked, its error is raised before anything is booked.
        """
        slots = [
            Interval(start, start + first.duration)
            for start in occurrences(first.start, rule)
            if not self.is_holiday(start.date())
        ]
        for slot in slots:
            self._check_bookable(room_id, slot)
        return [self.book(room_id, title, organizer, slot) for slot in slots]

    def cancel(self, booking_id: int) -> Booking:
        """Cancel a booking, which frees its room and stops its reminders."""
        cancelled = replace(self._bookings[booking_id], status=Status.CANCELLED)
        self._bookings[booking_id] = cancelled
        return cancelled

    def reschedule(self, booking_id: int, interval: Interval) -> Booking:
        """Move an active booking to a new time in the same room and re-arm its reminder."""
        booking = self._bookings[booking_id]
        if booking.status is not Status.ACTIVE:
            raise ValueError(f"booking {booking_id} is cancelled")
        self._check_bookable(booking.room_id, interval, ignore=booking_id)
        moved = replace(booking, interval=interval)
        self._bookings[booking_id] = moved
        self._reminders = [r for r in self._reminders if r.booking_id != booking_id]
        self._reminders.extend(reminders.reminders_for(moved))
        return moved

    def bookings_on(self, day: date, room_id: str | None = None) -> list[Booking]:
        """Return the active bookings on ``day``, earliest first, optionally of one room."""
        found = [
            booking
            for booking in self._bookings.values()
            if booking.status is Status.ACTIVE
            and booking.interval.start.date() == day
            and room_id in (None, booking.room_id)
        ]
        return sorted(found, key=lambda booking: (booking.interval.start, booking.booking_id))

    def bookings_for_room(self, room_id: str) -> list[Booking]:
        """Return every active booking of a room, earliest first."""
        found = [
            booking
            for booking in self._bookings.values()
            if booking.room_id == room_id and booking.status is Status.ACTIVE
        ]
        return sorted(found, key=lambda booking: (booking.interval.start, booking.booking_id))

    def pending_reminders(self, now: datetime) -> list[reminders.Reminder]:
        """Return the unsent reminders of active bookings that are due at ``now``."""
        due = [
            reminder
            for reminder in self._reminders
            if not reminder.sent
            and reminder.send_at <= now
            and self._bookings[reminder.booking_id].status is Status.ACTIVE
        ]
        return sorted(due, key=lambda reminder: (reminder.send_at, reminder.booking_id))

    def purge_cancelled(self, before: datetime) -> int:
        """Forget the cancelled bookings that ended before ``before``, with their reminders.

        Returns how many bookings were forgotten.
        """
        removed = 0
        for booking_id, booking in list(self._bookings.items()):
            if booking.status is Status.CANCELLED and booking.interval.end < before:
                del self._bookings[booking_id]
                removed += 1
        self._reminders = [r for r in self._reminders if r.booking_id in self._bookings]
        return removed

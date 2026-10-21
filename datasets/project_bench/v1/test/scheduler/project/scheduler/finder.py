"""Finding a free time or a free room for a meeting."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from scheduler.bookings import Calendar
from scheduler.rooms import Room, RoomDirectory
from scheduler.timeutil import Interval


def free_slots(calendar: Calendar, room_id: str, day: date, length: timedelta) -> list[Interval]:
    """Return every free slot of ``length`` in the room on ``day``, earliest first.

    Slots start on the quarter hour and lie within office hours, 08:00 to 18:00.
    A holiday has no free slots.
    """
    if calendar.is_holiday(day):
        return []
    start = datetime.combine(day, time(8, 0))
    closing = datetime.combine(day, time(18, 0))
    slots: list[Interval] = []
    while start + length <= closing:
        slot = Interval(start, start + length)
        if not calendar.conflicts(room_id, slot):
            slots.append(slot)
        start += timedelta(minutes=15)
    return slots


def find_room(
    directory: RoomDirectory,
    calendar: Calendar,
    interval: Interval,
    attendees: int,
    needs: Iterable[str] = (),
) -> Room | None:
    """Return the smallest suitable room that is free for the whole interval, or None."""
    for room in directory.suitable(attendees, needs):
        if not calendar.conflicts(room.room_id, interval):
            return room
    return None

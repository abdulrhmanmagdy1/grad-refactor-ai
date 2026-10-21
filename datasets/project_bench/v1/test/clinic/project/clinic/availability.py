"""Doctors' working hours and free appointment slots."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta

from clinic.models import Appointment, Doctor

DEFAULT_SLOT_MINUTES = 30


def within_working_hours(doctor: Doctor, start: datetime, end: datetime) -> bool:
    """True when the whole visit from ``start`` to ``end`` is inside the doctor's
    working hours of that day."""
    hours = doctor.hours.get(start.weekday())
    if hours is None:
        return False
    opens = datetime.combine(start.date(), hours[0])
    closes = datetime.combine(start.date(), hours[1])
    return opens <= start and end <= closes


def free_slots(
    doctor: Doctor,
    day: date,
    appointments: Iterable[Appointment],
    slot_minutes: int = DEFAULT_SLOT_MINUTES,
) -> list[datetime]:
    """Start times of the free slots of ``slot_minutes`` on ``day``, earliest first.

    Slots are laid out back to back from opening time and must end by closing time.
    A slot is free when no appointment that still holds its time overlaps it.
    """
    hours = doctor.hours.get(day.weekday())
    if hours is None:
        return []
    taken = [appointment for appointment in appointments if appointment.holds_time]
    step = timedelta(minutes=slot_minutes)
    slot = datetime.combine(day, hours[0])
    closes = datetime.combine(day, hours[1])
    slots: list[datetime] = []
    while slot + step <= closes:
        if not any(appointment.overlaps(slot, slot + step) for appointment in taken):
            slots.append(slot)
        slot += step
    return slots

"""Booking, cancelling and closing appointments."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from clinic.availability import DEFAULT_SLOT_MINUTES, free_slots
from clinic.models import ZERO, Appointment, AppointmentStatus, Doctor

LATE_CANCELLATION_NOTICE_HOURS = 24
LATE_CANCELLATION_FEE = Decimal("25.00")


def is_late_cancellation(start: datetime, now: datetime) -> bool:
    """True when cancelling at ``now`` gives less than LATE_CANCELLATION_NOTICE_HOURS
    of notice before the appointment at ``start``."""
    return start - now < timedelta(hours=LATE_CANCELLATION_NOTICE_HOURS)


class Schedule:
    """The clinic's appointments, kept in memory."""

    def __init__(self) -> None:
        self._appointments: dict[int, Appointment] = {}
        self._next_id = 1

    def get(self, appointment_id: int) -> Appointment:
        """Return the appointment with ``appointment_id``; KeyError when there is none."""
        return self._appointments[appointment_id]

    def for_doctor(self, doctor_id: int, day: date | None = None) -> list[Appointment]:
        """The doctor's appointments, all of them or those on ``day``, by start time."""
        found = [
            appointment
            for appointment in self._appointments.values()
            if appointment.doctor_id == doctor_id
            and (day is None or appointment.start.date() == day)
        ]
        return sorted(found, key=lambda appointment: appointment.start)

    def book(
        self,
        patient_id: int,
        doctor: Doctor,
        start: datetime,
        minutes: int = DEFAULT_SLOT_MINUTES,
    ) -> Appointment:
        """Book ``minutes`` with ``doctor`` from ``start`` and return the appointment.

        Raises ValueError when the visit is not inside the doctor's working hours, or
        when it overlaps another of the doctor's appointments that still holds its time.
        """
        if minutes <= 0:
            raise ValueError("an appointment needs a positive length")
        end = start + timedelta(minutes=minutes)
        hours = doctor.hours.get(start.weekday())
        if hours is None:
            raise ValueError(f"{doctor.name} does not work on {start:%A}s")
        opens = datetime.combine(start.date(), hours[0])
        closes = datetime.combine(start.date(), hours[1])
        if start < opens or end > closes:
            raise ValueError(f"{start:%H:%M}-{end:%H:%M} is outside {doctor.name}'s hours")
        for other in self.for_doctor(doctor.id, start.date()):
            if other.holds_time and other.overlaps(start, end):
                raise ValueError(f"{doctor.name} is already booked at {other.start:%H:%M}")
        appointment = Appointment(self._next_id, patient_id, doctor.id, start, end)
        self._appointments[appointment.id] = appointment
        self._next_id += 1
        return appointment

    def open_slots(
        self, doctor: Doctor, day: date, slot_minutes: int = DEFAULT_SLOT_MINUTES
    ) -> list[datetime]:
        """Start times of the doctor's free slots on ``day``."""
        return free_slots(doctor, day, self.for_doctor(doctor.id, day), slot_minutes)

    def cancel(self, appointment_id: int, now: datetime) -> Decimal:
        """Cancel a booked appointment and return the fee the patient owes for it.

        Only an appointment that is still booked can be cancelled; any other status
        raises ValueError. A late cancellation costs LATE_CANCELLATION_FEE, an
        earlier one costs nothing.
        """
        appointment = self.get(appointment_id)
        if appointment.status is not AppointmentStatus.BOOKED:
            raise ValueError(f"appointment {appointment_id} is {appointment.status.value}")
        appointment.status = AppointmentStatus.CANCELLED
        if is_late_cancellation(appointment.start, now):
            return LATE_CANCELLATION_FEE
        return ZERO

    def close(self, appointment_id: int, attended: bool = True) -> Appointment:
        """Close a booked appointment as completed, or as a no-show if the patient
        did not come."""
        appointment = self.get(appointment_id)
        if appointment.status is not AppointmentStatus.BOOKED:
            raise ValueError(f"appointment {appointment_id} is {appointment.status.value}")
        if attended:
            appointment.status = AppointmentStatus.COMPLETED
        else:
            appointment.status = AppointmentStatus.NO_SHOW
        return appointment

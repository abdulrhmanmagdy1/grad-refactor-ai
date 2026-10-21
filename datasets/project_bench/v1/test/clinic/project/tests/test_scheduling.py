from datetime import date, datetime, time
from decimal import Decimal

import pytest

from clinic.models import AppointmentStatus, Doctor
from clinic.scheduling import LATE_CANCELLATION_FEE, Schedule

MONDAY = date(2026, 3, 2)


def make_doctor() -> Doctor:
    hours = {0: (time(9), time(13)), 2: (time(14), time(18))}
    return Doctor(1, "Dr. Salma Nour", Decimal("200.00"), hours)


def at(hour: int, minute: int = 0, day: date = MONDAY) -> datetime:
    return datetime.combine(day, time(hour, minute))


def test_book_inside_working_hours():
    schedule = Schedule()
    appointment = schedule.book(7, make_doctor(), at(9, 30))
    assert appointment.end == at(10)
    assert appointment.status is AppointmentStatus.BOOKED
    assert schedule.get(appointment.id) is appointment


@pytest.mark.parametrize(
    "start",
    [at(8, 30), at(12, 45), datetime(2026, 3, 3, 10, 0)],
    ids=["before-opening", "past-closing", "day-off"],
)
def test_book_outside_working_hours(start):
    with pytest.raises(ValueError):
        Schedule().book(7, make_doctor(), start)


def test_overlapping_booking_is_refused():
    schedule = Schedule()
    doctor = make_doctor()
    schedule.book(1, doctor, at(10))
    with pytest.raises(ValueError):
        schedule.book(2, doctor, at(10, 15))


def test_back_to_back_bookings():
    schedule = Schedule()
    doctor = make_doctor()
    second = schedule.book(2, doctor, at(10, 30))
    first = schedule.book(1, doctor, at(10))
    assert schedule.for_doctor(doctor.id, MONDAY) == [first, second]


def test_open_slots_skip_booked_time():
    schedule = Schedule()
    doctor = make_doctor()
    schedule.book(1, doctor, at(10), minutes=60)
    assert schedule.open_slots(doctor, MONDAY) == [
        at(9),
        at(9, 30),
        at(11),
        at(11, 30),
        at(12),
        at(12, 30),
    ]


def test_late_cancellation_costs_the_fee_and_frees_the_slot():
    schedule = Schedule()
    doctor = make_doctor()
    appointment = schedule.book(1, doctor, at(11))
    assert schedule.cancel(appointment.id, now=at(8)) == LATE_CANCELLATION_FEE
    assert appointment.status is AppointmentStatus.CANCELLED
    assert at(11) in schedule.open_slots(doctor, MONDAY)


def test_close_appointment():
    schedule = Schedule()
    appointment = schedule.book(1, make_doctor(), at(11))
    schedule.close(appointment.id, attended=False)
    assert appointment.status is AppointmentStatus.NO_SHOW
    with pytest.raises(ValueError):
        schedule.close(appointment.id)

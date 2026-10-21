"""Hidden tests for the clinic benchmark project."""

import sqlite3
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from clinic.billing import build_invoice
from clinic.insurance import coverage_split
from clinic.models import ZERO, AppointmentStatus, Doctor, InsurancePolicy, Patient
from clinic.scheduling import LATE_CANCELLATION_FEE, Schedule, is_late_cancellation
from clinic.storage import PatientStore

MONDAY = date(2026, 3, 2)


def make_doctor() -> Doctor:
    return Doctor(1, "Dr. Salma Nour", Decimal("200.00"), {0: (time(9), time(17))})


def at(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(MONDAY, time(hour, minute))


def make_policy(valid_until: date = date(2026, 12, 31)) -> InsurancePolicy:
    return InsurancePolicy(
        patient_id=7,
        insurer="Nile Health",
        coverage_percent=80,
        annual_limit=Decimal("1000.00"),
        valid_from=date(2026, 1, 1),
        valid_until=valid_until,
    )


def completed_visit(schedule: Schedule, doctor: Doctor):
    appointment = schedule.book(7, doctor, at(10))
    return schedule.close(appointment.id)


def test_B1_a_cancelled_appointment_cannot_be_cancelled_again():
    schedule = Schedule()
    appointment = schedule.book(1, make_doctor(), at(11))
    schedule.cancel(appointment.id, now=at(8))
    with pytest.raises(ValueError):
        schedule.cancel(appointment.id, now=at(8, 30))


def test_B1_a_missed_appointment_cannot_be_cancelled():
    schedule = Schedule()
    appointment = schedule.book(1, make_doctor(), at(11))
    schedule.close(appointment.id, attended=False)
    with pytest.raises(ValueError):
        schedule.cancel(appointment.id, now=at(12))
    assert appointment.status is AppointmentStatus.NO_SHOW


def test_B2_cancelling_more_than_a_day_ahead_is_not_late():
    start = datetime(2026, 3, 12, 11, 0)
    assert not is_late_cancellation(start, start - timedelta(days=3, hours=2))
    assert not is_late_cancellation(start, start - timedelta(hours=25))
    assert not is_late_cancellation(start, start - timedelta(hours=24))


def test_B3_the_insurer_pays_the_covered_part():
    schedule = Schedule()
    doctor = make_doctor()
    invoice = build_invoice(completed_visit(schedule, doctor), doctor, make_policy())
    assert invoice.insurer_share == Decimal("160.00")
    assert invoice.patient_share == Decimal("40.00")
    assert invoice.insurer == "Nile Health"


def test_S1_search_does_not_run_sql_from_the_search_text():
    store = PatientStore()
    store.add_patients([Patient("Mona Hassan", date(1990, 5, 17)), Patient("Karim Adel", date(1984, 8, 1))])
    try:
        found = store.search_patients("' OR '1'='1")
    except (ValueError, sqlite3.Error):
        return
    assert found == []


def test_keep_search_matches_part_of_the_name_ignoring_case():
    store = PatientStore()
    store.add_patients(
        [
            Patient("Mona Hassan", date(1990, 5, 17)),
            Patient("Laila Omar", date(1979, 11, 2)),
            Patient("Karim Hassanein", date(1984, 8, 1)),
        ]
    )
    assert [patient.name for patient in store.search_patients("hassan")] == [
        "Karim Hassanein",
        "Mona Hassan",
    ]
    assert store.search_patients("zzz") == []


def test_keep_patients_by_ids_uses_bound_parameters():
    store = PatientStore()
    first, second = store.add_patients(
        [Patient("Amal", date(1980, 2, 2)), Patient("Basem", date(1985, 3, 3))]
    )
    assert [patient.name for patient in store.patients_by_ids([second.id, first.id])] == [
        "Amal",
        "Basem",
    ]
    assert store.patients_by_ids([first.id]) == [first]


def test_keep_failed_batch_stores_nothing_and_reraises():
    store = PatientStore()
    with pytest.raises(ValueError):
        store.add_patients([Patient("Amal", date(1980, 2, 2)), Patient(" ", date(1985, 3, 3))])
    assert store.count_patients() == 0
    store.add_patient(Patient("Basem", date(1985, 3, 3)))
    assert store.count_patients() == 1


def test_keep_short_notice_is_late():
    start = datetime(2026, 3, 12, 11, 0)
    assert is_late_cancellation(start, start - timedelta(hours=2))
    assert is_late_cancellation(start, start - timedelta(hours=23, minutes=59))


def test_keep_late_cancellation_costs_the_fee():
    schedule = Schedule()
    appointment = schedule.book(1, make_doctor(), at(11))
    assert schedule.cancel(appointment.id, now=at(9)) == LATE_CANCELLATION_FEE
    assert appointment.status is AppointmentStatus.CANCELLED


def test_keep_a_completed_visit_cannot_be_cancelled():
    schedule = Schedule()
    appointment = completed_visit(schedule, make_doctor())
    with pytest.raises(ValueError):
        schedule.cancel(appointment.id, now=at(12))
    assert appointment.status is AppointmentStatus.COMPLETED


def test_keep_back_to_back_but_not_overlapping():
    schedule = Schedule()
    doctor = make_doctor()
    schedule.book(1, doctor, at(10))
    schedule.book(2, doctor, at(10, 30))
    schedule.book(3, doctor, at(9, 30))
    with pytest.raises(ValueError):
        schedule.book(4, doctor, at(10, 45), minutes=15)
    with pytest.raises(ValueError):
        schedule.book(5, doctor, at(16, 45))


def test_keep_patient_pays_all_without_an_active_policy():
    schedule = Schedule()
    doctor = make_doctor()
    appointment = completed_visit(schedule, doctor)
    invoice = build_invoice(appointment, doctor, make_policy(valid_until=date(2026, 3, 1)))
    assert invoice.patient_share == Decimal("200.00")
    assert invoice.insurer_share == ZERO


def test_keep_coverage_split_rounds_and_adds_up():
    policy = InsurancePolicy(7, "Nile Health", 33, Decimal("1000.00"), MONDAY, MONDAY)
    assert coverage_split(Decimal("99.99"), policy) == (Decimal("66.99"), Decimal("33.00"))
    assert coverage_split(Decimal("200.00"), make_policy(), Decimal("1000.00")) == (
        Decimal("200.00"),
        ZERO,
    )

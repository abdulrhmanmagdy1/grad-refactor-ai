from datetime import date, datetime, time
from decimal import Decimal

import pytest

from clinic.billing import build_invoice, cancellation_invoice, render_invoice
from clinic.insurance import coverage_split, insurer_paid_in_year, policy_is_active
from clinic.models import ZERO, Appointment, AppointmentStatus, Doctor, InsurancePolicy, Invoice, Patient

DOCTOR = Doctor(3, "Dr. Omar Fathy", Decimal("200.00"), {0: (time(9), time(17))})
PATIENT = Patient("Mona Hassan", date(1990, 5, 17), "0100 555 0101", id=7)
POLICY = InsurancePolicy(
    patient_id=7,
    insurer="Nile Health",
    coverage_percent=80,
    annual_limit=Decimal("1000.00"),
    valid_from=date(2026, 1, 1),
    valid_until=date(2026, 12, 31),
)


def visit(status: AppointmentStatus = AppointmentStatus.COMPLETED) -> Appointment:
    start = datetime(2026, 3, 2, 10, 0)
    return Appointment(11, 7, 3, start, datetime(2026, 3, 2, 10, 30), status)


def test_invoice_without_insurance():
    invoice = build_invoice(visit(), DOCTOR)
    assert invoice.total == Decimal("200.00")
    assert invoice.patient_share == Decimal("200.00")
    assert invoice.insurer_share == ZERO
    assert invoice.issued_on == date(2026, 3, 2)


def test_only_completed_visits_are_invoiced():
    with pytest.raises(ValueError):
        build_invoice(visit(AppointmentStatus.BOOKED), DOCTOR)


def test_coverage_split():
    assert coverage_split(Decimal("200.00"), POLICY) == (Decimal("40.00"), Decimal("160.00"))
    assert coverage_split(Decimal("200.00"), POLICY, Decimal("950.00")) == (
        Decimal("150.00"),
        Decimal("50.00"),
    )


def test_policy_dates_are_inclusive():
    assert policy_is_active(POLICY, date(2026, 1, 1))
    assert policy_is_active(POLICY, date(2026, 12, 31))
    assert not policy_is_active(POLICY, date(2027, 1, 1))


def test_insurer_paid_in_year():
    invoices = [
        Invoice(1, 7, date(2026, 2, 1), Decimal("100"), Decimal("20"), Decimal("80")),
        Invoice(2, 7, date(2025, 2, 1), Decimal("100"), Decimal("20"), Decimal("80")),
        Invoice(3, 8, date(2026, 2, 1), Decimal("100"), Decimal("20"), Decimal("80")),
    ]
    assert insurer_paid_in_year(invoices, 7, 2026) == Decimal("80")


def test_render_invoice():
    appointment = visit()
    text = render_invoice(build_invoice(appointment, DOCTOR), PATIENT, DOCTOR, appointment)
    assert "Mona Hassan" in text
    assert "Consultation fee" in text
    assert "Amount due" in text
    assert "200.00" in text
    assert all(len(line) <= 48 for line in text.splitlines())


def test_cancellation_invoice():
    appointment = visit(AppointmentStatus.CANCELLED)
    invoice = cancellation_invoice(appointment, Decimal("25.00"), date(2026, 3, 2))
    assert (invoice.total, invoice.patient_share, invoice.insurer_share) == (
        Decimal("25.00"),
        Decimal("25.00"),
        ZERO,
    )
    assert "Late cancellation fee" in render_invoice(invoice, PATIENT, DOCTOR, appointment)

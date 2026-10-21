"""Invoices for visits and late cancellations, and their printed form."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from clinic.insurance import coverage_split, policy_is_active
from clinic.models import (
    ZERO,
    Appointment,
    AppointmentStatus,
    Doctor,
    InsurancePolicy,
    Invoice,
    Patient,
)

PAYMENT_TERM_DAYS = 14
INVOICE_WIDTH = 48


def build_invoice(
    appointment: Appointment,
    doctor: Doctor,
    policy: InsurancePolicy | None = None,
    already_paid: Decimal = ZERO,
    issued_on: date | None = None,
) -> Invoice:
    """Invoice a completed visit; the total is the doctor's fee.

    When the patient's policy is active on the day of the visit, the fee is split
    between patient and insurer with ``coverage_split``, passing what the insurer
    has ``already_paid`` this year. Otherwise the patient pays the whole fee.
    """
    if appointment.status is not AppointmentStatus.COMPLETED:
        raise ValueError(f"appointment {appointment.id} is {appointment.status.value}")
    if policy is not None and policy.patient_id != appointment.patient_id:
        raise ValueError("the policy belongs to another patient")
    total = doctor.fee
    patient_share, insurer_share, insurer = total, ZERO, ""
    if policy is not None and policy_is_active(policy, appointment.start.date()):
        insurer_share, patient_share = coverage_split(total, policy, already_paid)
        insurer = policy.insurer
    return Invoice(
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        issued_on=issued_on or appointment.start.date(),
        total=total,
        patient_share=patient_share,
        insurer_share=insurer_share,
        insurer=insurer,
    )


def cancellation_invoice(appointment: Appointment, fee: Decimal, issued_on: date) -> Invoice:
    """Invoice the patient for a late cancellation fee; insurance never pays it."""
    return Invoice(
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        issued_on=issued_on,
        total=fee,
        patient_share=fee,
    )


def _money(amount: Decimal) -> str:
    """Format an amount with a thousands separator and two decimals."""
    return f"{amount:,.2f}"


def render_invoice(
    invoice: Invoice,
    patient: Patient,
    doctor: Doctor,
    appointment: Appointment,
    clinic_name: str = "Riverside Family Clinic",
) -> str:
    """Return the invoice as plain text, INVOICE_WIDTH characters wide, for printing."""
    width = INVOICE_WIDTH
    lines: list[str] = []
    lines.append("=" * width)
    lines.append(clinic_name.center(width))
    lines.append("INVOICE".center(width))
    lines.append("=" * width)
    lines.append(f"Invoice for visit #{invoice.appointment_id}")
    lines.append(f"Issued on: {invoice.issued_on:%d %b %Y}")
    due = invoice.issued_on + timedelta(days=PAYMENT_TERM_DAYS)
    lines.append(f"Due by:    {due:%d %b %Y}")
    lines.append("")
    lines.append("Patient")
    lines.append(f"  Name:     {patient.name}")
    lines.append(f"  Born:     {patient.birth_date:%d %b %Y}")
    if patient.phone:
        lines.append(f"  Phone:    {patient.phone}")
    lines.append("")
    lines.append("Visit")
    lines.append(f"  Doctor:   {doctor.name}")
    lines.append(f"  Date:     {appointment.start:%A %d %b %Y}")
    lines.append(f"  Time:     {appointment.start:%H:%M}-{appointment.end:%H:%M}")
    minutes = int((appointment.end - appointment.start).total_seconds() // 60)
    lines.append(f"  Length:   {minutes} minutes")
    if appointment.status is AppointmentStatus.CANCELLED:
        lines.append("  Status:   cancelled at short notice")
    lines.append("")
    lines.append("-" * width)
    label = "Consultation fee"
    if appointment.status is AppointmentStatus.CANCELLED:
        label = "Late cancellation fee"
    amount = f"{invoice.total:,.2f}"
    lines.append(label + amount.rjust(width - len(label)))
    if invoice.insurer_share > ZERO:
        label = f"Paid by {invoice.insurer}"
        amount = f"-{invoice.insurer_share:,.2f}"
        lines.append(label + amount.rjust(width - len(label)))
        percent = invoice.insurer_share / invoice.total * 100
        lines.append(f"  ({percent:.0f}% of the fee)")
    lines.append("-" * width)
    label = "Amount due"
    amount = f"{invoice.patient_share:,.2f}"
    lines.append(label + amount.rjust(width - len(label)))
    lines.append("=" * width)
    if invoice.patient_share == ZERO:
        lines.append("Nothing to pay.".center(width))
    else:
        lines.append(f"Please pay within {PAYMENT_TERM_DAYS} days".center(width))
        lines.append("at the reception desk or by bank transfer,".center(width))
        lines.append(f"quoting invoice #{invoice.appointment_id}.".center(width))
    lines.append("")
    lines.append("Thank you for choosing us.".center(width))
    lines.append("=" * width)
    return "\n".join(lines)

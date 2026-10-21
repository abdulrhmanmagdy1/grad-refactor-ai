"""Insurance policies: when they apply and how a bill is split."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from clinic.models import CENT, ZERO, InsurancePolicy, Invoice


def policy_is_active(policy: InsurancePolicy, day: date) -> bool:
    """True when ``day`` is between the policy's first and last valid day, inclusive."""
    return policy.valid_from <= day <= policy.valid_until


def insurer_paid_in_year(invoices: Iterable[Invoice], patient_id: int, year: int) -> Decimal:
    """Total the insurer paid for ``patient_id`` on invoices issued in ``year``."""
    return sum(
        (
            invoice.insurer_share
            for invoice in invoices
            if invoice.patient_id == patient_id and invoice.issued_on.year == year
        ),
        ZERO,
    )


def coverage_split(
    amount: Decimal, policy: InsurancePolicy, already_paid: Decimal = ZERO
) -> tuple[Decimal, Decimal]:
    """Split ``amount`` into ``(patient_share, insurer_share)``.

    The insurer pays ``coverage_percent`` of the amount, rounded half up to the cent,
    but never more than is left of the annual limit after ``already_paid`` this
    year. The patient pays the rest, so the two shares add up to ``amount``.
    """
    if not 0 <= policy.coverage_percent <= 100:
        raise ValueError(f"coverage must be 0-100%, not {policy.coverage_percent}%")
    remaining = max(policy.annual_limit - already_paid, ZERO)
    covered = (amount * policy.coverage_percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    insurer_share = min(covered, remaining)
    return amount - insurer_share, insurer_share

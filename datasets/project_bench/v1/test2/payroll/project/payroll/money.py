"""Money helpers. All amounts are `Decimal`; floats never enter the payroll."""

from __future__ import annotations

from decimal import Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_cents(amount: Decimal) -> Decimal:
    """Round an amount to whole cents; half a cent always rounds up, as on the payslip."""
    return amount.quantize(CENT)


def prorate(amount: Decimal, part: int, whole: int) -> Decimal:
    """Return the share `part / whole` of `amount`, unrounded.

    `prorate(salary, 15, 30)` is half the salary.
    """
    if whole <= 0:
        raise ValueError("whole must be positive")
    return amount * part / whole


def parse_amount(text: str) -> Decimal:
    """Parse an amount such as '1,250.50' into a Decimal rounded to cents."""
    cleaned = text.replace(",", "").strip()
    if not cleaned:
        raise ValueError("empty amount")
    return to_cents(Decimal(cleaned))

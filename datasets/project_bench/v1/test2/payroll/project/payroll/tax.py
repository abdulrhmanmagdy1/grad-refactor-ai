"""Income tax brackets and statutory deductions, per month."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from payroll.money import ZERO, to_cents

PENSION_RATE = Decimal("0.05")
PENSION_CAP = Decimal("400.00")
HEALTH_INSURANCE = Decimal("25.00")


@dataclass(frozen=True)
class TaxBracket:
    """Income from `lower` up to `upper` (None = no limit) is taxed at `rate`."""

    lower: Decimal
    upper: Decimal | None
    rate: Decimal


MONTHLY_BRACKETS: tuple[TaxBracket, ...] = (
    TaxBracket(Decimal(0), Decimal(1000), Decimal(0)),
    TaxBracket(Decimal(1000), Decimal(3000), Decimal("0.10")),
    TaxBracket(Decimal(3000), Decimal(6000), Decimal("0.20")),
    TaxBracket(Decimal(6000), None, Decimal("0.30")),
)


def income_tax(taxable: Decimal, brackets: Sequence[TaxBracket] = MONTHLY_BRACKETS) -> Decimal:
    """Progressive tax: each slice of income is taxed at the rate of its own bracket.

    Brackets must be sorted and contiguous. Nothing is due on zero or negative income.
    """
    tax = Decimal(0)
    for bracket in brackets:
        if taxable <= bracket.lower:
            break
        top = taxable if bracket.upper is None else min(taxable, bracket.upper)
        tax += (top - bracket.lower) * bracket.rate
    return to_cents(tax)


def pension_contribution(gross: Decimal) -> Decimal:
    """The employee's pension contribution: 5% of gross pay, at most 400.00 a month."""
    return min(to_cents(gross * PENSION_RATE), PENSION_CAP)


def health_insurance(gross: Decimal) -> Decimal:
    """Flat monthly health insurance, charged only in months with some pay."""
    return HEALTH_INSURANCE if gross > 0 else ZERO

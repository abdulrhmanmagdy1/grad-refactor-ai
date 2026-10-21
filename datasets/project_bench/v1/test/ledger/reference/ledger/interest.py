"""Interest on savings: tiered annual rates, paid every month."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ledger.accounts import AccountKind
from ledger.money import CENT, ZERO

MONTHS_PER_YEAR = 12

# (lowest balance of the tier, annual rate as a fraction), highest tier first.
SAVINGS_TIERS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("25000.00"), Decimal("0.0200")),
    (Decimal("5000.00"), Decimal("0.0150")),
    (Decimal("0.00"), Decimal("0.0100")),
)


def rate_for_balance(kind: AccountKind, balance: Decimal) -> Decimal:
    """Return the annual rate an account of ``kind`` earns on ``balance``.

    A savings balance earns the rate of the highest tier it reaches; reaching a tier
    means being at or above its lowest balance. Checking accounts and negative
    balances earn nothing.
    """
    if kind is not AccountKind.SAVINGS or balance < ZERO:
        return ZERO
    for threshold, rate in SAVINGS_TIERS:
        if balance >= threshold:
            return rate
    return ZERO


def monthly_interest(balance: Decimal, annual_rate: Decimal) -> Decimal:
    """Return one month of interest on ``balance`` at ``annual_rate``.

    The interest is balance * annual_rate / 12, rounded half up to the cent like every
    other amount in the ledger. A balance of zero or less earns nothing.
    """
    if balance <= ZERO:
        return ZERO
    return (balance * annual_rate / MONTHS_PER_YEAR).quantize(CENT, rounding=ROUND_HALF_UP)


def projected_interest(kind: AccountKind, balance: Decimal, months: int) -> Decimal:
    """Return the interest ``balance`` would earn over ``months`` months.

    Each month's interest is added to the balance before the next month is worked
    out, and the tier is chosen again every month.
    """
    total = ZERO
    for _ in range(months):
        current = balance + total
        total += monthly_interest(current, rate_for_balance(kind, current))
    return total

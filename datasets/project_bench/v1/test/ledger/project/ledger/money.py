"""Money helpers. Every amount in the ledger is a Decimal rounded to the cent."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class AmountError(ValueError):
    """Raised when a value cannot be used as an amount of money."""


def to_money(value: Decimal | int | str) -> Decimal:
    """Return ``value`` as a Decimal rounded half up to the cent.

    Floats are refused because most cent amounts have no exact float value.
    """
    if isinstance(value, float):
        raise AmountError(f"pass a string or a Decimal, not a float: {value!r}")
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AmountError(f"not an amount of money: {value!r}") from exc
    if not amount.is_finite():
        raise AmountError(f"not an amount of money: {value!r}")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def positive_amount(value: Decimal | int | str) -> Decimal:
    """Return ``value`` as money, raising AmountError unless it is above zero."""
    amount = to_money(value)
    if amount <= ZERO:
        raise AmountError(f"amount must be above zero: {amount}")
    return amount


def format_money(amount: Decimal) -> str:
    """Format an amount with thousands separators and two decimals, e.g. ``-1,234.50``."""
    return f"{amount:,.2f}"

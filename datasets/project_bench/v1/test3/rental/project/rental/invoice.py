"""Invoices for returned rentals: days, extras, mileage, late days, damage and the deposit."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from rental import contracts
from rental.rates import EXTRA_DAILY_PRICES, LATE_DAY_SURCHARGE, ONE_WAY_FEE, rate_for

CENT = Decimal("0.01")


@dataclass(frozen=True)
class InvoiceLine:
    """One charge on an invoice."""

    description: str
    amount: Decimal


@dataclass
class Invoice:
    """The bill of one contract; the deposit held at pick-up is set against the total."""

    contract_number: str
    deposit_held: Decimal
    lines: list[InvoiceLine] = field(default_factory=list)

    def add(self, description: str, amount: Decimal) -> None:
        """Add a charge rounded to the cent; zero amounts are left off the invoice."""
        amount = amount.quantize(CENT, rounding=ROUND_HALF_UP)
        if amount:
            self.lines.append(InvoiceLine(description, amount))

    def amount_of(self, description: str) -> Decimal:
        """The amount of the line with ``description``, or zero when there is none."""
        for line in self.lines:
            if line.description == description:
                return line.amount
        return Decimal("0.00")

    @property
    def subtotal(self) -> Decimal:
        """Sum of all lines before tax."""
        return sum((line.amount for line in self.lines), Decimal("0.00"))

    @property
    def tax(self) -> Decimal:
        """Sales tax on the subtotal, rounded half up to the cent."""
        return (self.subtotal * Decimal("0.14")).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def total(self) -> Decimal:
        """Subtotal plus tax."""
        return self.subtotal + self.tax

    @property
    def balance_due(self) -> Decimal:
        """What the customer still owes after the deposit; negative means a refund."""
        return self.total - self.deposit_held


def excess_kilometres(driven: int, allowance: int) -> int:
    """Kilometres driven beyond the allowance; never negative."""
    return max(0, driven - allowance)


def mileage_charge(contract: contracts.Contract, odometer_in: int) -> Decimal:
    """Charge for the kilometres above ``km_per_day`` for each booked day."""
    rate = rate_for(contract.vehicle_class)
    allowance = rate.km_per_day * contracts.rental_days(contract.pickup_at, contract.due_at)
    driven = odometer_in - contract.odometer_out
    return rate.excess_per_km * excess_kilometres(driven, allowance)


def late_charge(contract: contracts.Contract, returned_at: datetime) -> Decimal:
    """Each late day costs the daily rate times ``LATE_DAY_SURCHARGE``."""
    rate = rate_for(contract.vehicle_class)
    days = contracts.late_days(returned_at, contract.due_at)
    return rate.daily_rate * LATE_DAY_SURCHARGE * days


def build_invoice(contract: contracts.Contract) -> Invoice:
    """Invoice a returned contract.

    Booked days at the class rate, each extra per booked day, the one-way fee,
    excess mileage, late days and damage, with the class deposit held.
    """
    if contract.returned_at is None or contract.odometer_in is None:
        raise ValueError(f"contract {contract.number} has not been returned")
    rate = rate_for(contract.vehicle_class)
    days = contracts.rental_days(contract.pickup_at, contract.due_at)
    bill = Invoice(contract.number, deposit_held=contract.deposit)
    bill.add(f"rental {contract.vehicle_class}", rate.daily_rate * days)
    for name in contract.extras:
        bill.add(f"extra {name}", EXTRA_DAILY_PRICES[name] * days)
    if contract.is_one_way:
        bill.add("one-way drop-off", ONE_WAY_FEE)
    bill.add("excess mileage", mileage_charge(contract, contract.odometer_in))
    bill.add("late return", late_charge(contract, contract.returned_at))
    bill.add("damage", contract.damage_charge)
    return bill


def quote(vehicle_class: str, days: int, extras: Sequence[str], one_way: bool) -> Decimal:
    """Estimated total with tax for a rental returned on time within its mileage."""
    rate = rate_for(vehicle_class)
    amount = rate.daily_rate * days
    amount += sum((EXTRA_DAILY_PRICES[name] * days for name in extras), Decimal("0.00"))
    if one_way:
        amount += ONE_WAY_FEE
    return (amount * Decimal("1.14")).quantize(CENT, rounding=ROUND_HALF_UP)

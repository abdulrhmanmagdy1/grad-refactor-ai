"""Rental contracts: renting a car at one branch and taking it back at another."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from rental import invoice
from rental.fleet import Fleet
from rental.rates import EXTRA_DAILY_PRICES, rate_for
from rental.staff import Staff

GRACE_PERIOD = timedelta(minutes=59)
MINIMUM_DRIVER_AGE = 21
YOUNG_DRIVER_AGE = 25
ZERO = Decimal("0.00")


def rental_days(start: datetime, end: datetime) -> int:
    """Number of billed days from ``start`` to ``end``.

    Every started 24-hour period counts as a whole day and a rental is billed
    for at least one day: 24 hours is one day, 24 hours and one minute is two.
    """
    if end < start:
        raise ValueError("end is before start")
    return max(1, (end - start) // timedelta(days=1))


def late_days(due_at: datetime, returned_at: datetime) -> int:
    """Started days late, counted from ``due_at``.

    A car that comes back no later than ``GRACE_PERIOD`` after it was due is on time.
    """
    if returned_at <= due_at + GRACE_PERIOD:
        return 0
    return rental_days(due_at, returned_at)


def _periods_overlap(
    first_start: datetime, first_end: datetime, second_start: datetime, second_end: datetime
) -> bool:
    """True when two half-open periods share at least one moment."""
    return first_start < second_end and second_start < first_end


@dataclass(frozen=True)
class Booking:
    """What the customer asks for at the counter."""

    plate: str
    driver_name: str
    driver_age: int
    dropoff_branch: str
    pickup_at: datetime
    days: int


@dataclass(frozen=True)
class ReturnReport:
    """What the counter records when a car comes back."""

    branch_code: str
    returned_at: datetime
    odometer: int
    damage_charge: Decimal = ZERO


@dataclass
class Contract:
    """One rental from pick-up to drop-off."""

    number: str
    plate: str
    vehicle_class: str
    driver_name: str
    pickup_branch: str
    dropoff_branch: str
    pickup_at: datetime
    due_at: datetime
    odometer_out: int
    deposit: Decimal
    extras: list[str] = field(default_factory=list)
    returned_at: datetime | None = None
    odometer_in: int | None = None
    damage_charge: Decimal = ZERO
    waiver_reason: str | None = None
    bill: invoice.Invoice | None = None

    @property
    def is_one_way(self) -> bool:
        """True when the car is dropped off at another branch."""
        return self.pickup_branch != self.dropoff_branch

    @property
    def is_open(self) -> bool:
        """True until the car has been returned."""
        return self.returned_at is None


class RentalDesk:
    """Opens and closes the rental contracts of every branch."""

    def __init__(self, fleet: Fleet) -> None:
        self.fleet = fleet
        self.contracts: dict[str, Contract] = {}
        self._numbers = itertools.count(1)

    def contract(self, number: str) -> Contract:
        """Return the contract with ``number``; an unknown number raises ``KeyError``."""
        return self.contracts[number]

    def open_contracts(self) -> list[Contract]:
        """Contracts whose car is still out, in the order they were opened."""
        return [c for c in self.contracts.values() if c.is_open]

    def open_contract(self, booking: Booking, extras: list[str] = []) -> Contract:
        """Rent the booked car from the branch it is parked at.

        Drivers under 21 are refused and drivers under 25 pay the young-driver
        surcharge, which is added to the contract's extras. The class deposit is
        held at pick-up.
        """
        if booking.driver_age < MINIMUM_DRIVER_AGE:
            raise ValueError("driver is under the minimum rental age")
        if booking.days < 1:
            raise ValueError("a rental lasts at least one day")
        unknown = [name for name in extras if name not in EXTRA_DAILY_PRICES]
        if unknown:
            raise ValueError(f"unknown extras: {', '.join(unknown)}")
        self.fleet.branch(booking.dropoff_branch)
        vehicle = self.fleet.check_out(booking.plate)
        if booking.driver_age < YOUNG_DRIVER_AGE:
            extras.append("young-driver")
        contract = Contract(
            number=f"RA-{next(self._numbers):05d}",
            plate=vehicle.plate,
            vehicle_class=vehicle.vehicle_class,
            driver_name=booking.driver_name,
            pickup_branch=vehicle.branch_code,
            dropoff_branch=booking.dropoff_branch,
            pickup_at=booking.pickup_at,
            due_at=booking.pickup_at + timedelta(days=booking.days),
            odometer_out=vehicle.odometer,
            deposit=rate_for(vehicle.vehicle_class).deposit,
            extras=extras,
        )
        self.contracts[contract.number] = contract
        return contract

    def return_vehicle(self, number: str, report: ReturnReport) -> invoice.Invoice:
        """Close a contract when its car comes back and return the invoice.

        The car must be returned at the drop-off branch agreed at pick-up.
        """
        contract = self.contract(number)
        if not contract.is_open:
            raise ValueError(f"contract {number} is already closed")
        if report.branch_code != contract.dropoff_branch:
            raise ValueError(f"contract {number} must be returned at {contract.dropoff_branch}")
        if report.returned_at < contract.pickup_at:
            raise ValueError("return time is before pick-up")
        self.fleet.check_in(contract.plate, report.branch_code, report.odometer)
        contract.returned_at = report.returned_at
        contract.odometer_in = report.odometer
        contract.damage_charge = report.damage_charge
        contract.bill = invoice.build_invoice(contract)
        return contract.bill

    def waive_damage(self, number: str, staff: Staff, reason: str) -> invoice.Invoice:
        """Cancel the damage charge of a returned contract and reissue its invoice.

        Only a manager of the branch where the car was returned may waive
        damage, and the reason is kept on the contract.
        """
        contract = self.contract(number)
        if contract.is_open:
            raise ValueError(f"contract {number} is still open")
        if staff.branch_code != contract.dropoff_branch:
            raise PermissionError(f"{staff.name} does not work at {contract.dropoff_branch}")
        if not reason.strip():
            raise ValueError("a reason is required to waive damage")
        contract.damage_charge = ZERO
        contract.waiver_reason = reason.strip()
        contract.bill = invoice.build_invoice(contract)
        return contract.bill

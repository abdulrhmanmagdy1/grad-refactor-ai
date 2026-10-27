"""Plain records shared by the pharmacy modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class Role(str, Enum):
    """The job a member of staff holds at the counter."""

    PHARMACIST = "pharmacist"
    TECHNICIAN = "technician"
    CASHIER = "cashier"


@dataclass(frozen=True)
class Staff:
    """A member of staff who can serve customers."""

    staff_id: str
    name: str
    role: Role
    active: bool = True


@dataclass(frozen=True)
class Medicine:
    """A medicine as listed in the pharmacy's formulary.

    ``max_single_mg`` is the largest amount a patient may take at one time and
    ``max_daily_mg`` the largest total over one day. Controlled medicines may only be
    sold after a pharmacist has approved the sale.
    """

    code: str
    name: str
    strength_mg: int
    unit_price: Decimal
    max_single_mg: int
    max_daily_mg: int
    controlled: bool = False


@dataclass
class Batch:
    """Units of one medicine from one delivery, sharing a lot number and expiry date."""

    medicine_code: str
    lot: str
    expiry: date
    quantity: int


@dataclass(frozen=True)
class Pick:
    """Units taken from one batch to fill part of an order."""

    medicine_code: str
    lot: str
    expiry: date
    quantity: int


@dataclass
class Prescription:
    """A doctor's prescription for one medicine.

    ``quantity`` is the number of units handed over at each fill. The first fill is not
    a refill, so a prescription with ``refills_allowed = 2`` can be filled three times.
    """

    rx_id: str
    patient: str
    medicine_code: str
    dose_mg: int
    times_per_day: int
    quantity: int
    issued: date
    refills_allowed: int = 0
    fills: list[date] = field(default_factory=list)

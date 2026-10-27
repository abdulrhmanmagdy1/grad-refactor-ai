"""The rate card: daily price, included kilometres and deposit per vehicle class."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ClassRate:
    """Prices for one vehicle class.

    ``km_per_day`` is the mileage included for each billed rental day; every
    kilometre above that allowance costs ``excess_per_km``. ``deposit`` is held
    on the customer's card at pick-up and settled against the invoice.
    """

    daily_rate: Decimal
    km_per_day: int
    excess_per_km: Decimal
    deposit: Decimal


RATE_CARD: dict[str, ClassRate] = {
    "economy": ClassRate(Decimal("32.00"), 200, Decimal("0.20"), Decimal("250.00")),
    "compact": ClassRate(Decimal("41.00"), 250, Decimal("0.22"), Decimal("300.00")),
    "suv": ClassRate(Decimal("68.00"), 300, Decimal("0.30"), Decimal("500.00")),
    "van": ClassRate(Decimal("74.00"), 300, Decimal("0.35"), Decimal("600.00")),
}

EXTRA_DAILY_PRICES: dict[str, Decimal] = {
    "child-seat": Decimal("7.50"),
    "gps": Decimal("5.00"),
    "extra-driver": Decimal("9.00"),
    "young-driver": Decimal("12.00"),
}

ONE_WAY_FEE = Decimal("55.00")
"""Flat fee when the car is dropped off at a branch other than the pick-up branch."""

LATE_DAY_SURCHARGE = Decimal("1.5")
"""Each late day costs the class daily rate times this factor."""


def rate_for(vehicle_class: str) -> ClassRate:
    """Return the rate of ``vehicle_class``; an unknown class raises ``ValueError``."""
    try:
        return RATE_CARD[vehicle_class]
    except KeyError:
        raise ValueError(f"unknown vehicle class: {vehicle_class!r}") from None

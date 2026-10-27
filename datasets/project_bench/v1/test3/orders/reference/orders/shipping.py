"""Shipping cost by parcel weight and destination zone."""

from __future__ import annotations

import math
from decimal import Decimal

from orders.utils import money, zone_for_country

# Zone -> (base fee, price per billable kilogram).
RATES: dict[str, tuple[Decimal, Decimal]] = {
    "domestic": (Decimal("3.90"), Decimal("0.90")),
    "eu": (Decimal("8.90"), Decimal("1.60")),
    "europe": (Decimal("12.90"), Decimal("2.40")),
    "world": (Decimal("19.90"), Decimal("4.50")),
}


def billable_kilos(weight_kg: Decimal) -> int:
    """Kilograms the carrier charges for: every started kilogram counts, at least one."""
    if weight_kg < 0:
        raise ValueError("weight cannot be negative")
    return max(1, math.ceil(weight_kg))


def shipping_cost(weight_kg: Decimal, country: str, subtotal: Decimal) -> Decimal:
    """Price of shipping a parcel to ``country``.

    The zone's base fee plus its per-kilogram price for each billable kilogram.
    Orders whose subtotal (before discounts) is 75.00 or more ship free.
    """
    if subtotal >= Decimal("75.00"):
        return Decimal("0.00")
    base, per_kg = RATES[zone_for_country(country)]
    return money(base + per_kg * billable_kilos(weight_kg))

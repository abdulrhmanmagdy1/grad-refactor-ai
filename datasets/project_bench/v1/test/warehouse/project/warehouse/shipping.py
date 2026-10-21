"""Packing orders into parcels and pricing the parcels with the carrier."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from warehouse.models import Parcel, Product

MAX_PARCEL_KG = 25.0

RATE_TABLE: tuple[tuple[int, float], ...] = (
    (2, 4.50),
    (5, 6.90),
    (10, 9.80),
    (25, 15.00),
)
"""Carrier price per parcel: each entry is (highest billable kg, price)."""


def billable_weight(weight_kg: float) -> int:
    """Weight the carrier charges for, in whole kilograms.

    Every started kilogram is charged as a full one, and no parcel is charged
    for less than 1 kg.
    """
    if not math.isfinite(weight_kg) or weight_kg <= 0:
        raise ValueError(f"invalid parcel weight: {weight_kg!r}")
    return max(1, round(weight_kg))


def parcel_price(weight_kg: float) -> float:
    """Carrier price for one parcel; ValueError when it is over the heaviest band."""
    billable = billable_weight(weight_kg)
    for heaviest, price in RATE_TABLE:
        if billable <= heaviest:
            return price
    raise ValueError(f"{weight_kg} kg is over the carrier's parcel limit")


def pack_order(
    order_id: str,
    quantities: Mapping[str, int],
    products: Mapping[str, Product],
) -> list[Parcel]:
    """Pack an order into parcels, first fit, heaviest units first.

    No parcel may weigh more than MAX_PARCEL_KG; a single unit over that limit
    raises ValueError.
    """
    parcels: list[Parcel] = []
    for sku in sorted(quantities, key=lambda code: products[code].weight_kg, reverse=True):
        weight = products[sku].weight_kg
        if weight > MAX_PARCEL_KG:
            raise ValueError(f"{sku} is too heavy to ship as a parcel")
        for _ in range(quantities[sku]):
            for parcel in parcels:
                if parcel.weight_kg + weight <= MAX_PARCEL_KG:
                    parcel.weight_kg += weight
                    if sku in parcel.items:
                        parcel.items[sku] += 1
                    else:
                        parcel.items[sku] = 1
                    break
            else:
                parcels.append(Parcel(order_id, weight, {sku: 1}))
    return parcels


def shipping_cost(parcels: Iterable[Parcel]) -> float:
    """Total carrier price of the given parcels, rounded to cents."""
    return round(sum(parcel_price(parcel.weight_kg) for parcel in parcels), 2)


def manifest(parcels: Iterable[Parcel]) -> list[str]:
    """Lines for the carrier's pickup sheet: order, parcel number and billable kg."""
    return [
        f"{parcel.order_id}/{number} {billable_weight(parcel.weight_kg)} kg"
        for number, parcel in enumerate(parcels, start=1)
    ]

"""Delivery fees by distance band."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from delivery.geo import distance_km
from delivery.models import Location

CENT = Decimal("0.01")

# (upper limit in km, fee) ordered by distance.
FEE_BANDS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("2"), Decimal("1.50")),
    (Decimal("5"), Decimal("2.90")),
    (Decimal("8"), Decimal("4.50")),
)

SMALL_ORDER_LIMIT = Decimal("12.00")
SMALL_ORDER_SURCHARGE = Decimal("1.00")


class OutOfRangeError(ValueError):
    """Raised when a customer is farther away than the last fee band."""


def rounded_distance(start: Location, end: Location) -> Decimal:
    """Return the distance between two points in km, rounded to 0.1 km."""
    km = Decimal(str(distance_km(start, end)))
    return km.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def band_fee(distance: Decimal) -> Decimal:
    """Return the fee of the band that covers ``distance`` km.

    Each band covers distances up to and including its upper limit, so a
    trip of exactly 5 km costs the 5 km band's fee. Raises OutOfRangeError
    beyond the last band.
    """
    if distance < 0:
        raise ValueError("distance cannot be negative")
    for upper, fee in FEE_BANDS:
        if distance <= upper:
            return fee
    raise OutOfRangeError(f"{distance} km is outside the delivery area")


def delivery_fee(restaurant_at: Location, customer_at: Location, subtotal: Decimal) -> Decimal:
    """Return the delivery fee for an order.

    The band fee for the rounded distance, plus a small-order surcharge when
    the food subtotal is below SMALL_ORDER_LIMIT.
    """
    fee = band_fee(rounded_distance(restaurant_at, customer_at))
    if subtotal < SMALL_ORDER_LIMIT:
        fee += SMALL_ORDER_SURCHARGE
    return fee.quantize(CENT)


def max_delivery_km() -> Decimal:
    """Return the largest distance the service delivers to."""
    return FEE_BANDS[-1][0]

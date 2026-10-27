from decimal import Decimal

import pytest

from delivery.fees import OutOfRangeError, band_fee, delivery_fee, max_delivery_km, rounded_distance
from delivery.models import Location


def test_band_fee_inside_bands() -> None:
    assert band_fee(Decimal("1.2")) == Decimal("1.50")
    assert band_fee(Decimal("3.7")) == Decimal("2.90")
    assert band_fee(Decimal("6.4")) == Decimal("4.50")


def test_band_fee_outside_area() -> None:
    with pytest.raises(OutOfRangeError):
        band_fee(Decimal("9.3"))


def test_negative_distance_is_rejected() -> None:
    with pytest.raises(ValueError):
        band_fee(Decimal("-1"))


def test_rounded_distance() -> None:
    assert rounded_distance(Location(0, 0), Location(0.03, 0)) == Decimal("3.3")


def test_small_order_surcharge() -> None:
    start, end = Location(0, 0), Location(0.03, 0)
    assert delivery_fee(start, end, Decimal("20.00")) == Decimal("2.90")
    assert delivery_fee(start, end, Decimal("9.00")) == Decimal("3.90")


def test_max_delivery_km() -> None:
    assert max_delivery_km() == Decimal("8")

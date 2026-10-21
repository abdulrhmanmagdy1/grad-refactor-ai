import pytest

from warehouse.models import Product
from warehouse.shipping import (
    billable_weight,
    manifest,
    pack_order,
    parcel_price,
    shipping_cost,
)

ANVIL = Product("ANVIL-S", "Small anvil", 40.0, 10.0, reorder_point=2, reorder_quantity=5)
TONGS = Product("TONGS-1", "Forge tongs", 12.0, 2.0, reorder_point=5, reorder_quantity=20)
PRODUCTS = {product.sku: product for product in (ANVIL, TONGS)}


def test_billable_weight_whole_kilograms() -> None:
    assert billable_weight(3.0) == 3
    assert billable_weight(0.4) == 1


def test_billable_weight_rejects_nonsense() -> None:
    with pytest.raises(ValueError):
        billable_weight(0)
    with pytest.raises(ValueError):
        billable_weight(float("nan"))


def test_parcel_price_follows_the_rate_table() -> None:
    assert parcel_price(2.0) == 4.50
    assert parcel_price(5.0) == 6.90
    assert parcel_price(18.0) == 15.00
    with pytest.raises(ValueError):
        parcel_price(30.0)


def test_pack_order_first_fit_heaviest_first() -> None:
    parcels = pack_order("SO-9", {"TONGS-1": 4, "ANVIL-S": 3}, PRODUCTS)
    assert [(parcel.weight_kg, parcel.items) for parcel in parcels] == [
        (24.0, {"ANVIL-S": 2, "TONGS-1": 2}),
        (14.0, {"ANVIL-S": 1, "TONGS-1": 2}),
    ]
    assert all(parcel.order_id == "SO-9" for parcel in parcels)


def test_pack_order_refuses_units_over_the_parcel_limit() -> None:
    crate = Product("CRATE", "Crate", 5.0, 26.0, reorder_point=1, reorder_quantity=1)
    with pytest.raises(ValueError, match="CRATE"):
        pack_order("SO-10", {"CRATE": 1}, {"CRATE": crate})


def test_shipping_cost_and_manifest() -> None:
    parcels = pack_order("SO-9", {"TONGS-1": 4, "ANVIL-S": 3}, PRODUCTS)
    assert shipping_cost(parcels) == 30.00
    assert manifest(parcels) == ["SO-9/1 24 kg", "SO-9/2 14 kg"]

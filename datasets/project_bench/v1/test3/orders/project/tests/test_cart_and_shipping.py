from decimal import Decimal

import pytest

from orders.cart import Cart
from orders.catalog import Catalog
from orders.shipping import shipping_cost


def test_adding_the_same_variant_merges_lines(catalog: Catalog) -> None:
    cart = Cart("c1")
    cart.add(catalog.variant("MUG"), 2)
    line = cart.add(catalog.variant("MUG"))
    assert line.quantity == 3
    assert list(cart.lines) == ["MUG"]
    assert cart.subtotal == Decimal("37.50")
    assert cart.weight_kg == Decimal("1.50")


def test_quantity_must_be_positive(catalog: Catalog) -> None:
    with pytest.raises(ValueError):
        Cart("c1").add(catalog.variant("MUG"), 0)


def test_remove_and_clear(catalog: Catalog) -> None:
    cart = Cart("c1")
    cart.add(catalog.variant("MUG"))
    cart.add(catalog.variant("SHIRT-S"), 2)
    cart.remove("MUG")
    assert cart.quantities() == {"SHIRT-S": 2}
    cart.clear()
    assert cart.subtotal == Decimal("0.00")


def test_free_shipping_gap(catalog: Catalog) -> None:
    cart = Cart("c1")
    cart.add(catalog.variant("SHIRT-M"), 2)
    assert cart.free_shipping_gap() == Decimal("35.00")
    cart.add(catalog.variant("SHIRT-M"), 2)
    assert cart.free_shipping_gap() == Decimal("0.00")


def test_shipping_cost_by_zone() -> None:
    assert shipping_cost(Decimal("2"), "de", Decimal("40.00")) == Decimal("5.70")
    assert shipping_cost(Decimal("2"), "FR", Decimal("40.00")) == Decimal("12.10")
    assert shipping_cost(Decimal("1"), "JP", Decimal("40.00")) == Decimal("24.40")


def test_light_parcels_pay_for_one_kilogram() -> None:
    assert shipping_cost(Decimal("0"), "DE", Decimal("10.00")) == Decimal("4.80")


def test_shipping_is_free_from_75() -> None:
    assert shipping_cost(Decimal("3"), "GB", Decimal("75.00")) == Decimal("0.00")


def test_negative_weight_is_rejected() -> None:
    with pytest.raises(ValueError):
        shipping_cost(Decimal("-1"), "DE", Decimal("10.00"))

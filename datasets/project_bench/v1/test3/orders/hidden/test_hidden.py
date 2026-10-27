import logging
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from orders.cart import Cart
from orders.catalog import Catalog, Product, Variant
from orders.checkout import Checkout
from orders.coupons import CouponBook
from orders.order import Order, OrderBook, OrderLine, Quote, RefundError
from orders.shipping import billable_kilos, shipping_cost
from orders.store import connect, orders_by_ids, save_order

TODAY = date(2026, 6, 1)


def make_catalog() -> Catalog:
    catalog = Catalog()
    lamp = Product("lamp", "Desk lamp")
    lamp.variants["LAMP"] = Variant("LAMP", "lamp", "Black", Decimal("30.00"), Decimal("1.20"), 10)
    lamp.variants["BULB"] = Variant("BULB", "lamp", "Bulb", Decimal("4.00"), Decimal("0.10"), 50)
    catalog.add_product(lamp)
    return catalog


def shipped_order(book: OrderBook, customer_id: str) -> Order:
    cart = Cart(customer_id)
    cart.add(book.catalog.variant("LAMP"))
    order = Checkout(book, CouponBook()).place_order(cart, "DE", TODAY)
    book.pay(order.order_id, order.total)
    book.ship(order.order_id, "staff-1")
    return order


def test_B1_each_order_has_its_own_history() -> None:
    prices = Quote(Decimal("30.00"), Decimal("0.00"), Decimal("0.00"), Decimal("30.00"))
    first = Order("A-1", "c1", [OrderLine("LAMP", 1, Decimal("30.00"))], prices)
    second = Order("A-2", "c2", [OrderLine("LAMP", 1, Decimal("30.00"))], prices)
    assert first.history == [("placed", "c1")]
    assert second.history == [("placed", "c2")]


def test_B1_timeline_shows_only_that_order() -> None:
    book = OrderBook(make_catalog())
    first = shipped_order(book, "c1")
    second = shipped_order(book, "c2")
    assert book.timeline(second.order_id) == [
        "placed by c2",
        "paid by payments",
        "shipped by staff-1",
    ]
    assert len(first.history) == 3


@pytest.mark.parametrize(
    ("weight", "kilos"),
    [("0.2", 1), ("1.0", 1), ("1.01", 2), ("1.2", 2), ("2.4", 3), ("2.5", 3), ("3.0", 3)],
)
def test_B2_every_started_kilogram_is_billed(weight: str, kilos: int) -> None:
    assert billable_kilos(Decimal(weight)) == kilos


def test_B2_shipping_cost_uses_started_kilograms() -> None:
    assert shipping_cost(Decimal("1.2"), "DE", Decimal("30.00")) == Decimal("5.70")


def test_B3_partial_refunds_cannot_exceed_the_payment() -> None:
    book = OrderBook(make_catalog())
    order = shipped_order(book, "c1")
    book.request_return(order.order_id, "c1")
    paid = order.paid
    assert book.refund(order.order_id, Decimal("20.00")) == paid - Decimal("20.00")
    with pytest.raises(RefundError):
        book.refund(order.order_id, paid - Decimal("10.00"))
    assert order.refunded == Decimal("20.00")
    assert book.refund(order.order_id, paid - Decimal("20.00")) == Decimal("0.00")
    with pytest.raises(RefundError):
        book.refund(order.order_id, Decimal("0.01"))


def test_S1_customer_cannot_return_someone_elses_order() -> None:
    catalog = make_catalog()
    book = OrderBook(catalog)
    order = shipped_order(book, "c1")
    with pytest.raises(PermissionError):
        book.request_return(order.order_id, "c2")
    assert order.state == "shipped"
    assert catalog.variant("LAMP").stock == 9


def test_keep_owner_can_return_and_stock_comes_back() -> None:
    catalog = make_catalog()
    book = OrderBook(catalog)
    order = shipped_order(book, "c1")
    assert book.request_return(order.order_id, "c1").state == "returned"
    assert catalog.variant("LAMP").stock == 10


def test_keep_full_refund_up_to_the_payment() -> None:
    book = OrderBook(make_catalog())
    cart = Cart("c1")
    cart.add(book.catalog.variant("BULB"), 3)
    order = Checkout(book, CouponBook()).place_order(cart, "DE", TODAY)
    book.pay(order.order_id, order.total)
    book.cancel(order.order_id, "c1")
    with pytest.raises(RefundError):
        book.refund(order.order_id, order.total + Decimal("0.01"))
    assert book.refund(order.order_id, order.total) == Decimal("0.00")
    assert order.refunded == order.paid


def test_keep_whole_kilograms_and_free_shipping() -> None:
    assert billable_kilos(Decimal("2")) == 2
    assert billable_kilos(Decimal("0")) == 1
    assert shipping_cost(Decimal("5.5"), "JP", Decimal("80.00")) == Decimal("0.00")


def test_keep_quote_adds_shipping_to_the_discounted_subtotal() -> None:
    cart = Cart("c9")
    cart.add(make_catalog().variant("LAMP"))
    checkout = Checkout(OrderBook(make_catalog()), CouponBook())
    prices, coupon = checkout.quote(cart, "FR", TODAY)
    assert coupon is None
    assert prices.total == prices.subtotal + prices.shipping


def test_keep_orders_by_ids_treats_ids_as_data(tmp_path: Path) -> None:
    book = OrderBook(make_catalog())
    order = shipped_order(book, "c1")
    conn = connect(tmp_path / "shop.db")
    save_order(conn, order)
    hostile = "x') OR 1=1 --"
    assert orders_by_ids(conn, [hostile]) == []
    assert orders_by_ids(conn, [order.order_id, hostile]) == [(order.order_id, "c1", "shipped")]
    conn.close()


def test_keep_failed_save_is_logged_and_raised(caplog: pytest.LogCaptureFixture) -> None:
    book = OrderBook(make_catalog())
    order = shipped_order(book, "c1")
    conn = sqlite3.connect(":memory:")
    with caplog.at_level(logging.ERROR, logger="orders.store"):
        with pytest.raises(sqlite3.OperationalError):
            save_order(conn, order)
    assert order.order_id in caplog.text
    conn.close()

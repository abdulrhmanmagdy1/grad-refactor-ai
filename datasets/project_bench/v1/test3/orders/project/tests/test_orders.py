from datetime import date
from decimal import Decimal

import pytest

from orders.cart import Cart
from orders.catalog import Catalog, StockError
from orders.checkout import Checkout, confirmation, summary_text
from orders.coupons import Coupon, CouponBook
from orders.order import OrderBook, OrderError, RefundError

TODAY = date(2026, 6, 1)


def order_for(catalog: Catalog, customer_id: str = "c1") -> tuple[OrderBook, str]:
    book = OrderBook(catalog)
    cart = Cart(customer_id)
    cart.add(catalog.variant("SHIRT-S"), 2)
    order = Checkout(book, CouponBook()).place_order(cart, "DE", TODAY)
    return book, order.order_id


def test_place_order_takes_stock_and_empties_the_cart(catalog: Catalog) -> None:
    coupons = CouponBook()
    coupons.add(Coupon("TEN", percent_off=Decimal("10")))
    cart = Cart("c1")
    cart.add(catalog.variant("MUG"), 2)
    book = OrderBook(catalog)
    order = Checkout(book, coupons).place_order(cart, "DE", TODAY, code="ten")
    assert order.order_id == "ORD-00001"
    assert order.total == Decimal("22.50") + Decimal("4.80")
    assert catalog.variant("MUG").stock == 8
    assert not cart.lines
    assert "c1" in coupons.coupons["TEN"].used_by


def test_out_of_stock_takes_nothing(catalog: Catalog) -> None:
    cart = Cart("c1")
    cart.add(catalog.variant("MUG"), 1)
    cart.add(catalog.variant("KETTLE"), 3)
    with pytest.raises(StockError):
        Checkout(OrderBook(catalog), CouponBook()).place_order(cart, "DE", TODAY)
    assert catalog.variant("MUG").stock == 10
    assert cart.lines


def test_summary_mentions_free_shipping_gap(catalog: Catalog) -> None:
    cart = Cart("c1")
    cart.add(catalog.variant("MUG"))
    prices, _ = Checkout(OrderBook(catalog), CouponBook()).quote(cart, "DE", TODAY)
    assert "Add 62.50 more for free shipping" in summary_text(prices)


def test_full_life_cycle_and_refund(catalog: Catalog) -> None:
    book, order_id = order_for(catalog)
    order = book.get(order_id)
    book.pay(order_id, order.total)
    book.ship(order_id, "staff-1")
    book.request_return(order_id, "c1")
    assert order.state == "returned"
    assert catalog.variant("SHIRT-S").stock == 5
    assert book.refund(order_id, order.total) == Decimal("0.00")


def test_payment_must_match_total(catalog: Catalog) -> None:
    book, order_id = order_for(catalog)
    with pytest.raises(OrderError):
        book.pay(order_id, Decimal("1.00"))


def test_only_the_owner_cancels(catalog: Catalog) -> None:
    book, order_id = order_for(catalog)
    with pytest.raises(PermissionError):
        book.cancel(order_id, "someone-else")
    book.cancel(order_id, "c1")
    assert catalog.variant("SHIRT-S").stock == 5


def test_shipped_order_cannot_be_cancelled(catalog: Catalog) -> None:
    book, order_id = order_for(catalog)
    book.pay(order_id, book.get(order_id).total)
    book.ship(order_id, "staff-1")
    with pytest.raises(OrderError):
        book.cancel(order_id, "c1")


def test_refund_needs_a_cancelled_or_returned_order(catalog: Catalog) -> None:
    book, order_id = order_for(catalog)
    book.pay(order_id, book.get(order_id).total)
    with pytest.raises(RefundError):
        book.refund(order_id, Decimal("5.00"))


def test_confirmation_lists_the_lines(catalog: Catalog) -> None:
    book, order_id = order_for(catalog)
    text = confirmation(book.get(order_id), "Lina")
    assert "2 x SHIRT-S at 20.00" in text
    assert "Total charged: 44.80" in text

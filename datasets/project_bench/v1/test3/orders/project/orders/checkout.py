"""Turning a cart into an order."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from orders.cart import Cart
from orders.coupons import Coupon, CouponBook
from orders.order import Order, OrderBook, OrderLine, Quote
from orders.shipping import shipping_cost
from orders.utils import confirmation_email, money


class CheckoutError(Exception):
    """Raised when a cart cannot be checked out."""


class Checkout:
    """Prices carts and turns them into orders in ``book``, using ``coupons``."""

    def __init__(self, book: OrderBook, coupons: CouponBook) -> None:
        self.book = book
        self.coupons = coupons

    def quote(
        self, cart: Cart, country: str, today: date, code: str | None = None
    ) -> tuple[Quote, Coupon | None]:
        """Price the cart for delivery to ``country``, with the coupon ``code`` if given."""
        subtotal = cart.subtotal
        coupon = self.coupons.validate(code, subtotal, cart.customer_id, today) if code else None
        discount = coupon.discount(subtotal) if coupon else Decimal("0.00")
        shipping = shipping_cost(cart.weight_kg, country, subtotal)
        return Quote(subtotal, discount, shipping, money(subtotal - discount + shipping)), coupon

    def place_order(self, cart: Cart, country: str, today: date, code: str | None = None) -> Order:
        """Place the cart as an order: price it, take the stock, use the coupon, empty the cart."""
        if not cart.lines:
            raise CheckoutError("the cart is empty")
        prices, coupon = self.quote(cart, country, today, code)
        self.book.catalog.reserve(cart.quantities())
        lines = [OrderLine(x.sku, x.quantity, x.unit_price) for x in cart.lines.values()]
        order = Order(self.book.next_id(), cart.customer_id, lines, prices)
        self.book.add(order)
        if coupon is not None:
            self.coupons.redeem(coupon, cart.customer_id)
        cart.clear()
        return order


def summary_text(prices: Quote) -> str:
    """The price summary shown on the checkout page."""
    rows = [f"Subtotal: {prices.subtotal:.2f}"]
    if prices.discount:
        rows.append(f"Discount: -{prices.discount:.2f}")
    if prices.shipping:
        rows.append(f"Shipping: {prices.shipping:.2f}")
        missing = Decimal("75.00") - prices.subtotal
        rows.append(f"Add {missing:.2f} more for free shipping")
    else:
        rows.append("Shipping: free")
    rows.append(f"Total: {prices.total:.2f}")
    return "\n".join(rows)


def confirmation(order: Order, customer_name: str) -> str:
    """The confirmation email for a placed order."""
    lines = [(line.sku, line.quantity, line.unit_price) for line in order.lines]
    return confirmation_email(order.order_id, customer_name, lines, order.total)

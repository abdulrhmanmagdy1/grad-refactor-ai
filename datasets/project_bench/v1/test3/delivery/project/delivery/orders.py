"""Placing, tracking and completing orders."""

from __future__ import annotations

import random
import string
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from delivery import fees, menu
from delivery.couriers import CourierPool
from delivery.estimates import estimate_minutes
from delivery.hours import is_open
from delivery.models import Location, Order, OrderLine, Restaurant

CENT = Decimal("0.01")
TOKEN_LENGTH = 16
TOKEN_ALPHABET = string.ascii_letters + string.digits


class OrderError(Exception):
    """Raised when an order cannot be placed or changed."""


def tip_amount(subtotal: Decimal, percent: Decimal) -> Decimal:
    """Return a tip of ``percent`` of the food subtotal, rounded half up to the cent."""
    if percent < 0:
        raise OrderError("tip cannot be negative")
    return (subtotal * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def new_tracking_token() -> str:
    """Return a fresh secret token that lets the customer follow an order.

    Anyone holding the token can see the courier's position, so it must not
    be guessable from other tokens.
    """
    return "".join(random.choices(TOKEN_ALPHABET, k=TOKEN_LENGTH))


class OrderService:
    """Takes orders for a set of restaurants and hands them to couriers."""

    def __init__(self, restaurants: list[Restaurant], pool: CourierPool) -> None:
        self._restaurants = {r.restaurant_id: r for r in restaurants}
        self._pool = pool
        self._orders: dict[str, Order] = {}
        self._by_token: dict[str, str] = {}
        self._next_number = 1

    def place(
        self,
        restaurant_id: str,
        lines: list[OrderLine],
        customer_at: Location,
        at: datetime,
        tip_percent: Decimal = Decimal("0"),
    ) -> Order:
        """Place an order, assign a courier if one is free and estimate the ETA."""
        restaurant = self._restaurants.get(restaurant_id)
        if restaurant is None:
            raise OrderError(f"unknown restaurant {restaurant_id!r}")
        if not is_open(restaurant, at):
            raise OrderError(f"{restaurant.name} is closed")
        try:
            food = menu.subtotal(restaurant, lines)
            fee = fees.delivery_fee(restaurant.location, customer_at, food)
        except (menu.MenuError, fees.OutOfRangeError) as exc:
            raise OrderError(str(exc)) from exc
        order = Order(
            order_id=f"O{self._next_number:05d}",
            restaurant_id=restaurant_id,
            customer_location=customer_at,
            lines=list(lines),
            subtotal=food,
            delivery_fee=fee,
            tip=tip_amount(food, tip_percent),
            tracking_token=new_tracking_token(),
        )
        self._next_number += 1
        courier = self._pool.assign(order, restaurant)
        if courier is not None:
            order.eta_minutes = estimate_minutes(restaurant, courier, customer_at, at)
        self._orders[order.order_id] = order
        self._by_token[order.tracking_token] = order.order_id
        return order

    def get(self, order_id: str) -> Order:
        """Return the order with this id."""
        return self._orders[order_id]

    def track(self, token: str) -> Order | None:
        """Return the order a tracking token belongs to, or None."""
        order_id = self._by_token.get(token)
        return None if order_id is None else self._orders[order_id]

    def mark_delivered(self, order_ids: set[str]) -> int:
        """Mark orders delivered and free their couriers; return how many were freed."""
        for order_id in order_ids:
            self._orders[order_id].status = "delivered"
        return self._pool.release_finished(order_ids)

    def revenue(self) -> Decimal:
        """Return the total of all delivered orders, tips included."""
        delivered = (o.total for o in self._orders.values() if o.status == "delivered")
        return sum(delivered, Decimal("0.00"))

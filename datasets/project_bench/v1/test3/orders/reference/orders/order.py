"""Orders and their life cycle: placed, paid, shipped, returned or cancelled, and refunds."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from orders.catalog import Catalog

TRANSITIONS: dict[str, set[str]] = {
    "placed": {"paid", "cancelled"},
    "paid": {"shipped", "cancelled"},
    "shipped": {"returned"},
    "returned": set(),
    "cancelled": set(),
}


class OrderError(Exception):
    """Raised when an order cannot move to the requested state."""


class RefundError(OrderError):
    """Raised when a refund is not allowed."""


@dataclass(frozen=True)
class Quote:
    """The amounts the customer sees before paying, and pays."""

    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    total: Decimal


@dataclass(frozen=True)
class OrderLine:
    """A sku, its quantity and the unit price charged."""

    sku: str
    quantity: int
    unit_price: Decimal


class Order:
    """A placed order.

    ``prices`` are the amounts quoted when it was placed. ``history`` records each
    state the order entered, with who moved it there.
    ``paid`` is the amount received and ``refunded`` the amount paid back so far.
    """

    def __init__(
        self,
        order_id: str,
        customer_id: str,
        lines: list[OrderLine],
        prices: Quote,
        history: list[tuple[str, str]] | None = None,
    ) -> None:
        self.order_id = order_id
        self.customer_id = customer_id
        self.lines = lines
        self.prices = prices
        self.state = "placed"
        self.paid = Decimal("0.00")
        self.refunded = Decimal("0.00")
        self.history = history if history is not None else []
        self.history.append(("placed", customer_id))

    @property
    def total(self) -> Decimal:
        """What the customer pays: subtotal minus discount plus shipping."""
        return self.prices.total

    def quantities(self) -> dict[str, int]:
        """Quantity per sku."""
        return {line.sku: line.quantity for line in self.lines}


class OrderBook:
    """Every order, by id. Customers may only act on their own orders."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.orders: dict[str, Order] = {}

    def next_id(self) -> str:
        """The id the next order will get."""
        return f"ORD-{len(self.orders) + 1:05d}"

    def add(self, order: Order) -> None:
        """Store a newly placed order."""
        self.orders[order.order_id] = order

    def get(self, order_id: str) -> Order:
        """Return the order with this id."""
        try:
            return self.orders[order_id]
        except KeyError:
            raise OrderError(f"unknown order {order_id}") from None

    def timeline(self, order_id: str) -> list[str]:
        """The order's history as readable lines."""
        return [f"{state} by {actor}" for state, actor in self.get(order_id).history]

    def pay(self, order_id: str, amount: Decimal) -> Order:
        """Record the payment of a placed order; it must match the order total."""
        order = self.get(order_id)
        if amount != order.total:
            raise OrderError(f"payment {amount} does not match total {order.total}")
        self._move(order, "paid", "payments")
        order.paid = amount
        return order

    def ship(self, order_id: str, staff_id: str) -> Order:
        """Mark a paid order as shipped."""
        order = self.get(order_id)
        self._move(order, "shipped", staff_id)
        return order

    def cancel(self, order_id: str, customer_id: str) -> Order:
        """Cancel the customer's own order before it ships and put the stock back.

        Raises PermissionError when the order belongs to another customer.
        """
        order = self.get(order_id)
        if order.customer_id != customer_id:
            raise PermissionError(f"{order_id} does not belong to {customer_id}")
        self._move(order, "cancelled", customer_id)
        self.catalog.release(order.quantities())
        return order

    def request_return(self, order_id: str, customer_id: str) -> Order:
        """Return the customer's own shipped order and put the stock back.

        Raises PermissionError when the order belongs to another customer.
        """
        order = self.get(order_id)
        if order.customer_id != customer_id:
            raise PermissionError(f"{order_id} does not belong to {customer_id}")
        self._move(order, "returned", customer_id)
        self.catalog.release(order.quantities())
        return order

    def refund(self, order_id: str, amount: Decimal) -> Decimal:
        """Pay back part or all of a cancelled or returned order.

        All refunds of an order together never exceed what was paid. Returns the
        amount that can still be refunded afterwards.
        """
        order = self.get(order_id)
        if order.state not in {"cancelled", "returned"}:
            raise RefundError(f"{order_id} is {order.state}; only cancelled or returned orders")
        if amount <= 0:
            raise RefundError("a refund must be a positive amount")
        remaining = order.paid - order.refunded
        if amount > remaining:
            raise RefundError(f"only {remaining} of {order_id} can still be refunded")
        order.refunded += amount
        return order.paid - order.refunded

    def _move(self, order: Order, state: str, actor: str) -> None:
        if state not in TRANSITIONS[order.state]:
            raise OrderError(f"{order.order_id} cannot go from {order.state} to {state}")
        order.state = state
        order.history.append((state, actor))

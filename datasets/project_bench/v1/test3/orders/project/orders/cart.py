"""Shopping carts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from orders.catalog import Variant


@dataclass(frozen=True)
class CartLine:
    """A variant in the cart with the price and weight it had when it was added."""

    sku: str
    quantity: int
    unit_price: Decimal
    weight_kg: Decimal

    @property
    def total(self) -> Decimal:
        """Price of the whole line."""
        return self.unit_price * self.quantity


class Cart:
    """A customer's cart, with at most one line per sku.

    The cart does not check stock; stock is checked when the order is placed.
    """

    def __init__(self, customer_id: str) -> None:
        self.customer_id = customer_id
        self.lines: dict[str, CartLine] = {}

    def add(self, variant: Variant, quantity: int = 1) -> CartLine:
        """Add ``quantity`` units of ``variant``, merging with an existing line."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        current = self.lines.get(variant.sku)
        total = quantity + (current.quantity if current else 0)
        line = CartLine(variant.sku, total, variant.price, variant.weight_kg)
        self.lines[variant.sku] = line
        return line

    def remove(self, sku: str) -> None:
        """Take a sku out of the cart."""
        del self.lines[sku]

    def clear(self) -> None:
        """Empty the cart."""
        self.lines.clear()

    @property
    def subtotal(self) -> Decimal:
        """Sum of the line totals."""
        return sum((line.total for line in self.lines.values()), Decimal("0.00"))

    @property
    def weight_kg(self) -> Decimal:
        """Weight of everything in the cart."""
        return sum((line.weight_kg * line.quantity for line in self.lines.values()), Decimal(0))

    def quantities(self) -> dict[str, int]:
        """Quantity per sku."""
        return {sku: line.quantity for sku, line in self.lines.items()}

    def free_shipping_gap(self) -> Decimal:
        """How much more the customer must spend to get free shipping; zero once reached."""
        return max(Decimal("0.00"), Decimal("75.00") - self.subtotal)

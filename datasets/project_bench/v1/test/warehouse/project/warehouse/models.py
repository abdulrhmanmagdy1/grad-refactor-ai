"""Records shared by the warehouse modules."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Product:
    """A stock-keeping unit with the figures used to reorder and ship it."""

    sku: str
    name: str
    unit_cost: float
    weight_kg: float
    reorder_point: int
    reorder_quantity: int


@dataclass
class OrderLine:
    """One line of a purchase order: units ordered and units received so far."""

    sku: str
    ordered: int
    received: int = 0


@dataclass
class PurchaseOrder:
    """An order placed with a supplier, received in one or more deliveries."""

    number: str
    supplier: str
    lines: list[OrderLine] = field(default_factory=list)

    def line_for(self, sku: str) -> OrderLine:
        """Return the line for ``sku``; raise KeyError when the order has none."""
        for line in self.lines:
            if line.sku == sku:
                return line
        raise KeyError(f"order {self.number} has no line for {sku}")

    @property
    def is_complete(self) -> bool:
        """True once every line has been received in full."""
        return all(line.received >= line.ordered for line in self.lines)


@dataclass(frozen=True)
class CustomerLine:
    """A quantity of one SKU that a customer order asks for."""

    order_id: str
    sku: str
    quantity: int


@dataclass(frozen=True)
class PickTask:
    """Take ``quantity`` units of ``sku`` from ``bin_code`` for ``order_id``."""

    order_id: str
    sku: str
    bin_code: str
    quantity: int


@dataclass
class Parcel:
    """One box handed to the carrier, with the units packed in it."""

    order_id: str
    weight_kg: float = 0.0
    items: dict[str, int] = field(default_factory=dict)

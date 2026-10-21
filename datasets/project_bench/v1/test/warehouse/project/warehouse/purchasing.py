"""Purchase orders: raising them, booking deliveries and suggesting reorders."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from warehouse.models import OrderLine, Product, PurchaseOrder
from warehouse.stock import StockLedger


def create_order(number: str, supplier: str, quantities: Mapping[str, int]) -> PurchaseOrder:
    """Return a new purchase order with one line per SKU, sorted by SKU.

    Every quantity must be positive and the order needs at least one line.
    """
    if not quantities:
        raise ValueError("a purchase order needs at least one line")
    bad = sorted(sku for sku, quantity in quantities.items() if quantity <= 0)
    if bad:
        raise ValueError(f"quantities must be positive: {', '.join(bad)}")
    lines = [OrderLine(sku, quantity) for sku, quantity in sorted(quantities.items())]
    return PurchaseOrder(number, supplier, lines)


def receive_line(order: PurchaseOrder, sku: str, quantity: int) -> int:
    """Record a delivery of ``quantity`` units against the order line for ``sku``.

    A delivery may complete a line but never take it past the quantity ordered:
    a quantity above what is still outstanding raises ValueError and records
    nothing. Returns the units still outstanding on the line afterwards.
    """
    if quantity <= 0:
        raise ValueError("delivered quantity must be positive")
    line = order.line_for(sku)
    outstanding = line.ordered - line.received
    if quantity > line.ordered:
        raise ValueError(f"{quantity} of {sku} is more than the {outstanding} outstanding")
    line.received += quantity
    return outstanding - quantity


def book_delivery(
    order: PurchaseOrder,
    ledger: StockLedger,
    bin_code: str,
    delivery: Mapping[str, int],
) -> list[str]:
    """Book a supplier delivery against ``order`` and put the goods away in ``bin_code``.

    Returns the SKUs whose lines this delivery completed, sorted.
    """
    completed = []
    for sku, quantity in sorted(delivery.items()):
        left = receive_line(order, sku, quantity)
        ledger.receive(sku, bin_code, quantity)
        if left == 0:
            completed.append(sku)
    return completed


def needs_reorder(product: Product, ledger: StockLedger) -> bool:
    """True when the stock available for ``product`` is at or below its reorder point."""
    return ledger.available(product.sku) <= product.reorder_point


def suggest_reorders(
    products: Iterable[Product],
    ledger: StockLedger,
    open_orders: Iterable[PurchaseOrder],
) -> dict[str, int]:
    """Units to reorder per SKU.

    Each product that needs reordering is suggested at its reorder quantity,
    unless an open purchase order still has units of it on the way.
    """
    on_the_way = {
        line.sku
        for order in open_orders
        for line in order.lines
        if line.received < line.ordered
    }
    return {
        product.sku: product.reorder_quantity
        for product in products
        if needs_reorder(product, ledger) and product.sku not in on_the_way
    }

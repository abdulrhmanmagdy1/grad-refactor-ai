"""Stock reports for the office: stock value, low stock and a CSV extract."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence

from warehouse.models import Product
from warehouse.stock import StockLedger


def stock_value(products: Iterable[Product], ledger: StockLedger) -> float:
    """Value of the units on hand at unit cost, rounded to cents."""
    return round(sum(product.unit_cost * ledger.on_hand(product.sku) for product in products), 2)


def low_stock(products: Iterable[Product], ledger: StockLedger) -> list[Product]:
    """Products that need reordering, sorted by SKU."""
    flagged = []
    for product in products:
        free = ledger.on_hand(product.sku) - ledger.reserved(product.sku)
        if free <= product.reorder_point:
            flagged.append(product)
    return sorted(flagged, key=lambda product: product.sku)


def stock_csv(products: Iterable[Product], ledger: StockLedger) -> str:
    """CSV text, one row per product by SKU: sku, name, on hand, reserved, available."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["sku", "name", "on_hand", "reserved", "available"])
    for product in sorted(products, key=lambda item: item.sku):
        sku = product.sku
        writer.writerow(
            [sku, product.name, ledger.on_hand(sku), ledger.reserved(sku), ledger.available(sku)]
        )
    return buffer.getvalue()


def summary(products: Sequence[Product], ledger: StockLedger) -> str:
    """Three-line text summary: SKU count, stock value and the SKUs to reorder."""
    to_reorder = ", ".join(product.sku for product in low_stock(products, ledger))
    return "\n".join(
        [
            f"SKUs: {len(products)}",
            f"Stock value: {stock_value(products, ledger):.2f}",
            f"Reorder: {to_reorder or 'none'}",
        ]
    )

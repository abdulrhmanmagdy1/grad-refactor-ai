"""Helpers used across the shop."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

CENT = Decimal("0.01")

ZONES: dict[str, str] = {"DE": "domestic", "CH": "europe", "GB": "europe", "NO": "europe"}
ZONES.update(dict.fromkeys(["AT", "BE", "ES", "FR", "IT", "NL"], "eu"))

CSV_FIELDS = ["order_id", "customer_id", "state", "total", "refunded"]


def money(amount: Decimal) -> Decimal:
    """Round an amount to whole cents, halves rounded away from zero."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def normalize_code(code: str) -> str:
    """Coupon codes ignore case, surrounding spaces and dashes: ' summer-10 ' is SUMMER10."""
    return code.strip().upper().replace("-", "")


def zone_for_country(country: str) -> str:
    """Shipping zone for an ISO country code; countries not listed are in 'world'."""
    return ZONES.get(country.strip().upper(), "world")


def confirmation_email(
    order_id: str, customer_name: str, lines: list[tuple[str, int, Decimal]], total: Decimal
) -> str:
    """Body of the order confirmation email; ``lines`` are (sku, quantity, unit price)."""
    rows = [f"Hello {customer_name},", "", f"thank you for order {order_id}:", ""]
    for sku, quantity, unit_price in lines:
        rows.append(f"  {quantity} x {sku} at {unit_price:.2f}")
    rows += ["", f"Total charged: {total:.2f}", "", "We will email you again when it ships."]
    return "\n".join(rows)


def export_orders_csv(rows: Iterable[dict[str, str]], path: Path) -> int:
    """Write order rows to a CSV file with a header line; returns the number of rows."""
    written = list(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(written)
    return len(written)

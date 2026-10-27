"""Sales reporting per event and export to CSV."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from ticketing.models import Event, Order, TicketStatus
from ticketing.pricing import tier_for_seat


@dataclass(frozen=True)
class TierLine:
    """One row of the sales report."""

    tier: str
    seats_total: int
    seats_sold: int
    revenue_cents: int


def _checksum(data: bytes) -> str:
    """Checksum written beside an export so a truncated or corrupted copy can be spotted."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def sales_by_tier(event: Event, orders: list[Order]) -> list[TierLine]:
    """Seats sold and revenue for each tier of ``event``, in the event's tier order.

    Refunded tickets count neither as sold nor as revenue. Revenue is what customers
    actually paid for their seats, after discounts and without booking fees.
    """
    capacity = {tier.name: 0 for tier in event.tiers}
    for seat in event.venue.seats:
        capacity[tier_for_seat(event, seat).name] += 1
    sold = {tier.name: 0 for tier in event.tiers}
    revenue = {tier.name: 0 for tier in event.tiers}
    for order in orders:
        if order.event_id != event.event_id:
            continue
        for ticket in order.tickets:
            if ticket.status is TicketStatus.REFUNDED:
                continue
            sold[ticket.tier] += 1
            revenue[ticket.tier] += ticket.paid_cents
    return [
        TierLine(tier.name, capacity[tier.name], sold[tier.name], revenue[tier.name])
        for tier in event.tiers
    ]


def export_sales_csv(lines: list[TierLine], directory: Path) -> Path:
    """Write the tier report to ``sales.csv`` in ``directory`` with a checksum file beside it."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["tier", "seats_total", "seats_sold", "revenue"])
    for line in lines:
        writer.writerow(
            [line.tier, line.seats_total, line.seats_sold, f"{line.revenue_cents / 100:.2f}"]
        )
    data = buffer.getvalue().encode("utf-8")
    target = directory / "sales.csv"
    target.write_bytes(data)
    (directory / "sales.csv.md5").write_text(_checksum(data), encoding="utf-8")
    return target


def export_orders_csv(orders: list[Order], directory: Path) -> Path:
    """Write one line per order to ``orders.csv`` in ``directory`` with a checksum file beside it."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["order", "customer", "tickets", "total"])
    for order in orders:
        writer.writerow(
            [order.order_id, order.customer, len(order.tickets), f"{order.total_cents / 100:.2f}"]
        )
    data = buffer.getvalue().encode("utf-8")
    target = directory / "orders.csv"
    target.write_bytes(data)
    (directory / "orders.csv.md5").write_text(_checksum(data), encoding="utf-8")
    return target

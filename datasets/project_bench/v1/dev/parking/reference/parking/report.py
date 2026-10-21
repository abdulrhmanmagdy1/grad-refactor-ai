"""Revenue reports for the garage office."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from parking.models import Permit, Ticket
from parking.permits import PermitRegistry
from parking.storage import TicketLog

CENT = Decimal("0.01")


def to_money(amount: float) -> float:
    """An amount rounded to cents, halves up (2.345 becomes 2.35)."""
    return float(Decimal(str(amount)).quantize(CENT, rounding=ROUND_HALF_UP))


def vat_split(gross: float) -> tuple[float, float]:
    """The net amount and the VAT part of a gross amount, both rounded to cents."""
    net = gross / 1.2
    return to_money(net), to_money(gross - net)


def daily_revenue(tickets: list[Ticket]) -> dict[date, float]:
    """Parking revenue per day; a stay counts on the day the car left."""
    totals: dict[date, float] = {}
    for ticket in tickets:
        if ticket.exited is not None:
            day = ticket.exited.date()
            totals[day] = to_money(totals.get(day, 0.0) + ticket.amount)
    return totals


def busiest_days(tickets: list[Ticket], count: int = 3) -> list[tuple[date, float]]:
    """The `count` days with the most parking revenue, the highest first."""
    totals = daily_revenue(tickets)
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)[:count]


def revenue_report(tickets: list[Ticket], permits: list[Permit], year: int, month: int) -> str:
    """A text report of one month's revenue.

    Parking counts on the day the car left and permits on the day they start. The report
    lists parking per day and per level, the number of stays and how many were free, the
    average stay, permit sales, and the grand total with its VAT part.
    """
    lines = [f"Revenue {year}-{month:02d}", ""]
    in_month = [
        ticket
        for ticket in tickets
        if ticket.exited is not None
        and ticket.exited.year == year
        and ticket.exited.month == month
    ]
    days = daily_revenue(in_month)
    lines.append("Parking by day")
    for day in sorted(days):
        lines.append(f"  {day.isoformat()}  {days[day]:>10.2f}")
    levels: dict[str, float] = {}
    for ticket in in_month:
        levels[ticket.level] = to_money(levels.get(ticket.level, 0.0) + ticket.amount)
    lines.append("Parking by level")
    for level in sorted(levels):
        lines.append(f"  {level:<10}  {levels[level]:>10.2f}")
    stays = len(in_month)
    free = sum(1 for ticket in in_month if ticket.amount == 0)
    minutes = 0.0
    for ticket in in_month:
        if ticket.exited is not None:
            minutes += (ticket.exited - ticket.entered).total_seconds() / 60
    average = round(minutes / stays) if stays else 0
    lines.append("")
    lines.append(f"Stays: {stays} ({free} free), average {average} min")
    sold = [
        permit
        for permit in permits
        if permit.start.year == year and permit.start.month == month
    ]
    permit_total = to_money(sum(permit.price for permit in sold))
    lines.append(f"Permits sold: {len(sold)}")
    parking_total = to_money(sum(days.values()))
    total = to_money(parking_total + permit_total)
    net, vat = vat_split(total)
    lines.append("")
    lines.append(f"Parking   {parking_total:>10.2f}")
    lines.append(f"Permits   {permit_total:>10.2f}")
    lines.append(f"Total     {total:>10.2f}")
    lines.append(f"  net     {net:>10.2f}")
    lines.append(f"  VAT     {vat:>10.2f}")
    return "\n".join(lines)


def report_from_log(log: TicketLog, permits: PermitRegistry, year: int, month: int) -> str:
    """The monthly report for everything in the ticket log and the permit registry."""
    return revenue_report(log.all(), permits.sold, year, month)

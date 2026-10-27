"""Monthly sales forecast built from the open deals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from crm.models import Deal

WIN_CHANCE: dict[str, Decimal] = {
    "lead": Decimal("0.10"),
    "qualified": Decimal("0.25"),
    "proposal": Decimal("0.50"),
    "negotiation": Decimal("0.75"),
}


@dataclass
class MonthForecast:
    """Expected revenue of the open deals planned to close in one month."""

    month: str
    deals: int
    pipeline: Decimal
    weighted: Decimal


def months_ahead(start: date, count: int) -> list[str]:
    """Return ``count`` month labels (YYYY-MM) starting with the month of ``start``."""
    labels = []
    year, month = start.year, start.month
    for _ in range(count):
        labels.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return labels


def forecast(deals: list[Deal], start: date, months: int = 3) -> list[MonthForecast]:
    """Group open deals by expected close month for the next ``months`` months.

    ``pipeline`` is the full amount of the deals, ``weighted`` the amount
    multiplied by the win chance of each deal's stage. Won and lost deals
    and deals outside the horizon are left out; a deal whose expected
    close date has already passed counts in the first month.
    """
    labels = months_ahead(start, months)
    rows = {label: MonthForecast(label, 0, Decimal("0.00"), Decimal("0.00")) for label in labels}
    for deal in deals:
        if deal.stage not in WIN_CHANCE:
            continue
        label = max(f"{deal.expected_close:%Y-%m}", labels[0])
        row = rows.get(label)
        if row is None:
            continue
        row.deals += 1
        row.pipeline += deal.amount
        row.weighted += (deal.amount * WIN_CHANCE[deal.stage]).quantize(Decimal("0.01"))
    return [rows[label] for label in labels]


def render(rows: list[MonthForecast]) -> str:
    """Return the forecast as a plain text table with a total line."""
    lines = [f"{'month':<8} {'deals':>5} {'pipeline':>12} {'weighted':>12}"]
    lines += [f"{r.month:<8} {r.deals:>5} {r.pipeline:>12} {r.weighted:>12}" for r in rows]
    total = sum((row.weighted for row in rows), Decimal("0.00"))
    lines.append(f"{'total':<8} {sum(r.deals for r in rows):>5} {'':>12} {total:>12}")
    return "\n".join(lines)

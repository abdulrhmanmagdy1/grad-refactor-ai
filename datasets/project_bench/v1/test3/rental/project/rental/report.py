"""Branch reports for the morning briefing at each counter."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from rental.contracts import Contract, RentalDesk, late_days
from rental.fleet import VehicleStatus


@dataclass(frozen=True)
class BranchSummary:
    """What one branch needs to know at the start of the day."""

    branch_code: str
    available_by_class: dict[str, int]
    cars_out: int
    returns_expected: int
    revenue: Decimal


def branch_summary(desk: RentalDesk, branch_code: str) -> BranchSummary:
    """Summarise a branch.

    ``cars_out`` counts open contracts picked up at the branch,
    ``returns_expected`` open contracts to be dropped off there, and
    ``revenue`` the invoice totals of contracts returned there.
    """
    desk.fleet.branch(branch_code)
    available = Counter(
        v.vehicle_class
        for v in desk.fleet.vehicles_at(branch_code)
        if v.status is VehicleStatus.AVAILABLE
    )
    open_contracts = desk.open_contracts()
    revenue = sum(
        (
            c.bill.total
            for c in desk.contracts.values()
            if c.bill is not None and c.dropoff_branch == branch_code
        ),
        Decimal("0.00"),
    )
    return BranchSummary(
        branch_code=branch_code,
        available_by_class=dict(sorted(available.items())),
        cars_out=sum(1 for c in open_contracts if c.pickup_branch == branch_code),
        returns_expected=sum(1 for c in open_contracts if c.dropoff_branch == branch_code),
        revenue=revenue,
    )


def overdue_contracts(desk: RentalDesk, now: datetime) -> list[Contract]:
    """Open contracts that are late at ``now`` (past the grace period), most overdue first."""
    overdue = [c for c in desk.open_contracts() if late_days(c.due_at, now) > 0]
    return sorted(overdue, key=lambda c: c.due_at)

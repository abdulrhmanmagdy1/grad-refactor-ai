"""Monthly billing: plan fees, extra charges and invoices."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from gym import memberships
from gym.models import Membership

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Charge:
    """One amount owed by a member."""

    member_id: str
    amount: Decimal
    description: str


@dataclass
class Invoice:
    """Everything a member owes for one month (``month`` is ``YYYY-MM``)."""

    member_id: str
    month: str
    charges: list[Charge] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        """Sum of the invoice's charges."""
        return sum((charge.amount for charge in self.charges), Decimal("0.00"))


class Ledger:
    """Collects the charges of the month that is being billed.

    ``close_month`` turns the collected charges into invoices; after it, the
    ledger holds no pending charges, so the next month starts empty.
    """

    def __init__(self) -> None:
        self.pending: dict[str, list[Charge]] = {}
        self.invoices: list[Invoice] = []

    def charge(self, member_id: str, amount: Decimal, description: str) -> Charge:
        """Record a positive amount owed by ``member_id`` this month."""
        if amount <= 0:
            raise ValueError("a charge must be a positive amount")
        entry = Charge(member_id, amount, description)
        self.pending.setdefault(member_id, []).append(entry)
        return entry

    def close_month(self, year: int, month: int) -> list[Invoice]:
        """Issue one invoice per member with pending charges, ordered by member id."""
        label = f"{year:04d}-{month:02d}"
        issued = [
            Invoice(member_id, label, list(charges))
            for member_id, charges in sorted(self.pending.items())
            if charges
        ]
        self.invoices.extend(issued)
        return issued


def prorated_fee(membership: Membership, year: int, month: int) -> Decimal:
    """The plan's monthly fee scaled by the share of the month the membership covers."""
    covered = memberships.active_days(membership, year, month)
    days_in_month = calendar.monthrange(year, month)[1]
    share = Decimal(covered) / Decimal(days_in_month)
    return (membership.plan.monthly_fee * share).quantize(CENT, rounding=ROUND_HALF_UP)


def bill_plan_fees(
    book: memberships.MembershipBook, ledger: Ledger, year: int, month: int
) -> list[Charge]:
    """Charge every membership its plan fee for the month; nothing for unused months."""
    charged = []
    for member_id in sorted(book.memberships):
        fee = prorated_fee(book.memberships[member_id], year, month)
        if fee > 0:
            charged.append(ledger.charge(member_id, fee, f"plan fee {year:04d}-{month:02d}"))
    return charged

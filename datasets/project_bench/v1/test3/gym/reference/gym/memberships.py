"""Registering members and selling, freezing and cancelling memberships."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from gym import billing
from gym.models import Member, Membership, Plan

FREEZE_FEE = Decimal("5.00")
CENT = Decimal("0.01")


class MembershipError(Exception):
    """Raised when a membership operation is not allowed."""


def active_days(membership: Membership, year: int, month: int) -> int:
    """Count the days of the given month on which the membership can be used."""
    days_in_month = calendar.monthrange(year, month)[1]
    return sum(
        1 for day in range(1, days_in_month + 1) if membership.covers(date(year, month, day))
    )


class MembershipBook:
    """The registered members and the current membership of each of them.

    Fees that are not part of the monthly plan fee (freezes, for example) are
    charged to ``ledger`` when they happen.
    """

    def __init__(self, ledger: billing.Ledger) -> None:
        self.members: dict[str, Member] = {}
        self.memberships: dict[str, Membership] = {}
        self.ledger = ledger

    def register(self, member: Member) -> None:
        """Add a new member; member ids are unique."""
        if member.member_id in self.members:
            raise MembershipError(f"member {member.member_id} already exists")
        self.members[member.member_id] = member

    def sell(self, member_id: str, plan: Plan, starts: date) -> Membership:
        """Start a membership on ``plan`` on ``starts``, replacing any earlier one.

        It lasts ``plan.duration_days`` days counting the first day.
        """
        if member_id not in self.members:
            raise MembershipError(f"unknown member {member_id}")
        expires = starts + timedelta(days=plan.duration_days - 1)
        membership = Membership(member_id, plan, starts, expires)
        self.memberships[member_id] = membership
        return membership

    def freeze(self, member_id: str, first_day: date, last_day: date) -> Membership:
        """Freeze the membership from ``first_day`` through ``last_day``, both included.

        The member cannot check in on those days, the expiry date moves later by
        the number of frozen days, the days count against the plan's
        ``max_freeze_days`` and the freeze fee is charged.
        """
        membership = self.get(member_id)
        if last_day < first_day:
            raise MembershipError("a freeze cannot end before it starts")
        days = (last_day - first_day).days + 1
        if membership.frozen_days + days > membership.plan.max_freeze_days:
            raise MembershipError("not enough freeze days left on this plan")
        membership.freezes.append((first_day, last_day))
        membership.frozen_days += days
        membership.expires += timedelta(days=days)
        self.ledger.charge(member_id, FREEZE_FEE, f"freeze from {first_day.isoformat()}")
        return membership

    def cancel(self, member_id: str, effective: date) -> Decimal:
        """End the membership on ``effective`` and return the refund owed.

        The member keeps access through ``effective``. The refund is the share of
        the monthly fee for the days of that month after ``effective`` that the
        membership would still have covered.
        """
        membership = self.get(member_id)
        days_in_month = calendar.monthrange(effective.year, effective.month)[1]
        month_end = effective.replace(day=days_in_month)
        unused = max(0, (min(membership.expires, month_end) - effective).days)
        membership.expires = effective
        share = Decimal(unused) / Decimal(days_in_month)
        return (membership.plan.monthly_fee * share).quantize(CENT, rounding=ROUND_HALF_UP)

    def get(self, member_id: str) -> Membership:
        """Return the member's current membership."""
        try:
            return self.memberships[member_id]
        except KeyError:
            raise MembershipError(f"{member_id} has no membership") from None

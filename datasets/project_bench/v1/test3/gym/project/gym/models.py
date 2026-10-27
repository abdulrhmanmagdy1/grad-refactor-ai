"""Plain records shared by the gym modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Plan:
    """A membership plan that members can buy.

    A new membership on the plan lasts ``duration_days`` days, the member pays
    ``monthly_fee`` for every calendar month it covers, and the membership may be
    frozen for at most ``max_freeze_days`` days in total.
    """

    code: str
    name: str
    monthly_fee: Decimal
    duration_days: int
    max_freeze_days: int = 30


@dataclass
class Member:
    """A person registered at the gym."""

    member_id: str
    name: str
    email: str


@dataclass
class Membership:
    """A member's subscription to a plan.

    The membership is valid from ``starts`` through ``expires``, both days included,
    except on the days inside one of its ``freezes`` (each freeze is a pair of first
    and last frozen day, both included). ``frozen_days`` counts the freeze days used.
    """

    member_id: str
    plan: Plan
    starts: date
    expires: date
    frozen_days: int = 0
    freezes: list[tuple[date, date]] = field(default_factory=list)

    def covers(self, day: date) -> bool:
        """Return True when the member may use the gym on ``day``."""
        if not self.starts <= day <= self.expires:
            return False
        return not any(first <= day <= last for first, last in self.freezes)

"""What a stay in the garage costs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from parking.report import to_money


def billable_hours(minutes: float) -> int:
    """Hours to bill for a stay of `minutes`: every started hour counts in full."""
    hours, rest = divmod(minutes, 60)
    return int(hours) + (1 if rest > 0 else 0)


@dataclass(frozen=True)
class RateCard:
    """The prices of the garage.

    Every started hour costs `hourly`, but one 24-hour period never costs more than
    `daily_cap`: a longer stay pays the cap for each full 24 hours, and the hourly rate,
    capped the same way, for the hours after the last full day. Stays of up to
    `grace_minutes` are free.
    """

    hourly: float
    daily_cap: float
    grace_minutes: int = 15

    def charge(self, entered: datetime, exited: datetime) -> float:
        """The price of a stay, rounded to cents."""
        if exited < entered:
            raise ValueError("a car cannot leave before it arrived")
        minutes = (exited - entered).total_seconds() / 60
        if minutes <= self.grace_minutes:
            return 0.0
        hours = billable_hours(minutes)
        days, rest = divmod(hours, 24)
        return to_money(days * self.daily_cap + min(rest * self.hourly, self.daily_cap))

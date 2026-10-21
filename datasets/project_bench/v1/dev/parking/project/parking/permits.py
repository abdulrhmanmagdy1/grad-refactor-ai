"""Monthly permits: a car with a valid permit parks free."""

from __future__ import annotations

import calendar
from datetime import date

from parking.models import Permit

MONTHLY_PRICE = 90.0


def add_months(start: date, months: int) -> date:
    """The same day `months` later, moved back to the last day of a shorter month."""
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class PermitRegistry:
    """The current permit of every plate, and every permit ever sold."""

    def __init__(self, monthly_price: float = MONTHLY_PRICE) -> None:
        self.monthly_price = monthly_price
        self.permits: dict[str, Permit] = {}
        self.sold: list[Permit] = []

    def issue(self, plate: str, holder: str, start: date, months: int = 1) -> Permit:
        """Sell a permit for `months` whole months from `start`; it replaces any older one."""
        if months < 1:
            raise ValueError("a permit runs for at least one month")
        permit = Permit(plate, holder, start, add_months(start, months), months * self.monthly_price)
        self.permits[plate] = permit
        self.sold.append(permit)
        return permit

    def is_valid(self, plate: str, day: date) -> bool:
        """True when the plate has a permit that covers `day`."""
        permit = self.permits.get(plate)
        return permit is not None and permit.start <= day < permit.expires

    def cancel(self, plate: str) -> None:
        """Withdraw a plate's permit; what was sold stays in `sold`."""
        if self.permits.pop(plate, None) is None:
            raise KeyError(f"{plate} has no permit")

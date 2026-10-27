"""Tier prices and discount codes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ticketing.models import Event, PriceTier, Seat


class PricingError(ValueError):
    """Raised when a seat cannot be priced or a discount code cannot be used."""


@dataclass
class DiscountCode:
    """A percentage discount that can be redeemed a limited number of times.

    ``max_uses`` is the total number of orders that may use the code and
    ``times_used`` counts the orders that already did.
    """

    code: str
    percent_off: int
    max_uses: int
    expires_at: datetime
    times_used: int = 0


def tier_for_seat(event: Event, seat: Seat) -> PriceTier:
    """Return the price tier that covers the seat's row."""
    for tier in event.tiers:
        if seat.row in tier.rows:
            return tier
    raise PricingError(f"no price tier covers row {seat.row} of {event.event_id}")


def apply_discount(price_cents: int, percent_off: int) -> int:
    """Return ``price_cents`` reduced by ``percent_off`` percent, rounded to the nearest cent."""
    if not 0 <= percent_off <= 100:
        raise PricingError(f"discount must be between 0 and 100 percent, got {percent_off}")
    return int(price_cents * (100 - percent_off) / 100)


class DiscountBook:
    """The discount codes on offer, looked up case-insensitively."""

    def __init__(self) -> None:
        self._codes: dict[str, DiscountCode] = {}

    def add(self, code: DiscountCode) -> None:
        """Register a code, replacing any earlier code with the same name."""
        self._codes[code.code.upper()] = code

    def get(self, code: str) -> DiscountCode | None:
        """Return the code registered under ``code``, or None."""
        return self._codes.get(code.upper())

    def redeem(self, code: str, now: datetime) -> DiscountCode:
        """Validate ``code`` for one order and count that use.

        Raises PricingError when the code is unknown, expired or used up.
        """
        found = self.get(code)
        if found is None:
            raise PricingError(f"unknown discount code {code!r}")
        if now >= found.expires_at:
            raise PricingError(f"discount code {code!r} has expired")
        if found.times_used > found.max_uses:
            raise PricingError(f"discount code {code!r} has been used up")
        found.times_used += 1
        return found

"""Seat maps with temporary holds while a customer checks out."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from ticketing.models import Event, Seat

HOLD_DURATION = timedelta(minutes=10)


class SeatUnavailableError(Exception):
    """Raised when a seat is sold, held by someone else, or a hold is no longer active."""


@dataclass
class Hold:
    """Seats reserved for one customer until ``expires_at``."""

    hold_id: str
    customer: str
    seats: frozenset[Seat]
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        """A hold lapses at ``expires_at``: from that instant its seats are free again."""
        return now >= self.expires_at


class SeatMap:
    """Tracks which seats of one event are free, held or sold."""

    def __init__(self, event: Event) -> None:
        self.event = event
        self._venue_seats = set(event.venue.seats)
        self._sold: set[Seat] = set()
        self._holds: dict[str, Hold] = {}

    def held_seats(self, now: datetime) -> set[Seat]:
        """Seats covered by holds that are still active at ``now``."""
        live = (hold for hold in self._holds.values() if not hold.is_expired(now))
        return {seat for hold in live for seat in hold.seats}

    def sold_seats(self) -> set[Seat]:
        """Seats that have been paid for and not refunded."""
        return set(self._sold)

    def available(self, now: datetime) -> set[Seat]:
        """Seats that are neither sold nor held at ``now``."""
        return self._venue_seats - self._sold - self.held_seats(now)

    def hold(self, customer: str, seats: list[Seat], now: datetime) -> Hold:
        """Hold ``seats`` for ``customer`` for HOLD_DURATION; all of them or none."""
        self.release_expired(now)
        free = self.available(now)
        missing = [seat.label for seat in seats if seat not in free]
        if missing:
            raise SeatUnavailableError(f"seats not available: {', '.join(missing)}")
        hold = Hold(uuid.uuid4().hex, customer, frozenset(seats), now + HOLD_DURATION)
        self._holds[hold.hold_id] = hold
        return hold

    def release_expired(self, now: datetime) -> int:
        """Drop every hold that has expired at ``now`` and return how many were dropped."""
        dropped = 0
        for hold_id, hold in list(self._holds.items()):
            if hold.is_expired(now):
                del self._holds[hold_id]
                dropped += 1
        return dropped

    def active_hold(self, hold_id: str, customer: str, now: datetime) -> Hold:
        """Return the hold if it belongs to ``customer`` and has not expired."""
        hold = self._holds.get(hold_id)
        if hold is None or hold.customer != customer or hold.is_expired(now):
            raise SeatUnavailableError(f"hold {hold_id} is not active for {customer}")
        return hold

    def complete(self, hold: Hold) -> None:
        """Turn a hold into sold seats."""
        self._holds.pop(hold.hold_id, None)
        self._sold |= hold.seats

    def release_sold(self, seat: Seat) -> None:
        """Put a refunded seat back on sale."""
        self._sold.discard(seat)

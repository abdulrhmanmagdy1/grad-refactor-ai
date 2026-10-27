"""Core data types for venues, events, tickets and orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TicketStatus(Enum):
    """Lifecycle of an issued ticket."""

    VALID = "valid"
    REFUNDED = "refunded"


@dataclass(frozen=True)
class Seat:
    """A physical seat, identified by its row letter and its number within the row."""

    row: str
    number: int

    @property
    def label(self) -> str:
        """Human-readable seat label such as ``"C12"``."""
        return f"{self.row}{self.number}"


@dataclass
class Venue:
    """A venue and the seats it offers."""

    name: str
    seats: list[Seat]

    @classmethod
    def with_rows(cls, name: str, rows: str, seats_per_row: int) -> Venue:
        """Build a rectangular venue: one row per letter of ``rows``, seats numbered from 1."""
        seats = [Seat(row, number) for row in rows for number in range(1, seats_per_row + 1)]
        return cls(name, seats)


@dataclass(frozen=True)
class PriceTier:
    """A price band that applies to every seat in a set of rows."""

    name: str
    rows: frozenset[str]
    price_cents: int


@dataclass
class Event:
    """A dated performance at a venue, priced by tier."""

    event_id: str
    title: str
    venue: Venue
    starts_at: datetime
    tiers: list[PriceTier]


@dataclass
class Ticket:
    """One seat sold for one event.

    ``base_price_cents`` is the tier price of the seat; ``paid_cents`` is what the
    customer was charged for the seat after any discount, booking fee excluded.
    """

    code: str
    event_id: str
    seat: Seat
    tier: str
    base_price_cents: int
    paid_cents: int
    status: TicketStatus = TicketStatus.VALID


@dataclass
class Order:
    """A completed purchase of one or more tickets for a single event."""

    order_id: str
    customer: str
    event_id: str
    tickets: list[Ticket]
    booking_fee_cents: int
    discount_code: str | None = None
    placed_at: datetime = field(default_factory=datetime.now)

    @property
    def total_cents(self) -> int:
        """Amount charged: the seats after discount plus the booking fee."""
        return sum(ticket.paid_cents for ticket in self.tickets) + self.booking_fee_cents

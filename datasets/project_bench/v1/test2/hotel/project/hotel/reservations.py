"""Reservations, room availability and the reservation book."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from hotel import cancellation
from hotel.rates import RateTable, nights_between
from hotel.rooms import Room, RoomCatalog

logger = logging.getLogger(__name__)


class Status(Enum):
    """Where a reservation is in its life."""

    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"


@dataclass
class Reservation:
    """One guest's stay in one room, from the check-in day to the check-out day."""

    reference: str
    guest: str
    room_number: str
    check_in: date
    check_out: date
    price: Decimal
    status: Status = Status.CONFIRMED
    special_requests: list[str] = field(default_factory=list)
    cancellation_fee: Decimal = Decimal("0.00")

    @property
    def nights(self) -> int:
        """Number of nights in the stay."""
        return (self.check_out - self.check_in).days

    @property
    def is_active(self) -> bool:
        """Whether the reservation still holds its room."""
        return self.status in (Status.CONFIRMED, Status.CHECKED_IN)

    def overlaps(self, check_in: date, check_out: date) -> bool:
        """Whether this stay shares at least one night with the stay check_in..check_out.

        The guest leaves on the check-out day, so the room is free again for a guest
        who arrives that same day.
        """
        return self.check_in <= check_out and check_in <= self.check_out


def _from_record(record: Mapping[str, str]) -> Reservation:
    """Build a reservation from a record written by `ReservationBook.records`."""
    requests = record.get("special_requests", "")
    return Reservation(
        reference=record["reference"],
        guest=record["guest"],
        room_number=record["room_number"],
        check_in=date.fromisoformat(record["check_in"]),
        check_out=date.fromisoformat(record["check_out"]),
        price=Decimal(record["price"]),
        status=Status(record["status"]),
        special_requests=[item for item in requests.split("|") if item],
        cancellation_fee=Decimal(record.get("cancellation_fee", "0.00")),
    )


class ReservationBook:
    """All reservations of the hotel, with the availability rules for new bookings."""

    def __init__(self, catalog: RoomCatalog, rates: RateTable) -> None:
        self._catalog = catalog
        self._rates = rates
        self._reservations: list[Reservation] = []
        self._next_number = 1

    def all(self) -> list[Reservation]:
        """Return every reservation in the order they were made."""
        return list(self._reservations)

    def get(self, reference: str) -> Reservation:
        """Return the reservation with this reference, or raise KeyError."""
        for reservation in self._reservations:
            if reservation.reference == reference:
                return reservation
        raise KeyError(f"no reservation {reference}")

    def is_available(self, room_number: str, check_in: date, check_out: date) -> bool:
        """Whether the room is in service and no active reservation holds it on those nights."""
        if not self._catalog.room(room_number).in_service:
            return False
        return not any(
            reservation.is_active
            and reservation.room_number == room_number
            and reservation.overlaps(check_in, check_out)
            for reservation in self._reservations
        )

    def available_rooms(self, type_code: str, check_in: date, check_out: date) -> list[Room]:
        """Return the rooms of one type that are free for the whole stay."""
        return [
            room
            for room in self._catalog.rooms_of_type(type_code)
            if self.is_available(room.number, check_in, check_out)
        ]

    def reserve(
        self,
        guest: str,
        room_number: str,
        check_in: date,
        check_out: date,
        special_requests: list[str] = [],
    ) -> Reservation:
        """Book a room for a stay and return the new, confirmed reservation."""
        nights_between(check_in, check_out)
        room = self._catalog.room(room_number)
        if not self.is_available(room_number, check_in, check_out):
            raise ValueError(f"room {room_number} is not free for that stay")
        reservation = Reservation(
            reference=f"R{self._next_number:05d}",
            guest=guest,
            room_number=room_number,
            check_in=check_in,
            check_out=check_out,
            price=self._rates.stay_price(room.room_type, check_in, check_out),
            special_requests=special_requests,
        )
        self._next_number += 1
        self._reservations.append(reservation)
        return reservation

    def add_request(self, reference: str, request: str) -> None:
        """Note a special request (extra pillow, late arrival...) on a reservation."""
        self.get(reference).special_requests.append(request)

    def cancel(self, reference: str, today: date) -> Decimal:
        """Cancel a confirmed reservation and return the fee the guest owes for it."""
        reservation = self.get(reference)
        if reservation.status is not Status.CONFIRMED:
            raise ValueError("only confirmed reservations can be cancelled")
        fee = cancellation.fee_for(reservation, today)
        reservation.status = Status.CANCELLED
        reservation.cancellation_fee = fee
        return fee

    def purge_cancelled(self, before: date) -> int:
        """Drop cancelled reservations whose stay ended before `before`; return how many."""
        removed = 0
        for reservation in list(self._reservations):
            if reservation.status is Status.CANCELLED and reservation.check_out < before:
                self._reservations.remove(reservation)
                removed += 1
        return removed

    def records(self) -> list[dict[str, str]]:
        """Export every reservation as a flat record of strings."""
        return [
            {
                "reference": r.reference,
                "guest": r.guest,
                "room_number": r.room_number,
                "check_in": r.check_in.isoformat(),
                "check_out": r.check_out.isoformat(),
                "price": str(r.price),
                "status": r.status.value,
                "special_requests": "|".join(r.special_requests),
                "cancellation_fee": str(r.cancellation_fee),
            }
            for r in self._reservations
        ]

    def restore(self, records: Iterable[Mapping[str, str]]) -> int:
        """Load records exported by `records` and return how many were loaded.

        A record that cannot be read is logged with its reference and the error is
        passed on to the caller.
        """
        loaded = 0
        for record in records:
            try:
                reservation = _from_record(record)
            except Exception:
                logger.exception("cannot restore reservation %s", record.get("reference"))
                raise
            self._reservations.append(reservation)
            self._next_number = max(self._next_number, int(reservation.reference[1:]) + 1)
            loaded += 1
        return loaded

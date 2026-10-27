"""Front-office reports: occupancy, arrivals and departures, revenue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from hotel.rates import to_money
from hotel.reservations import Reservation, ReservationBook, Status
from hotel.rooms import RoomCatalog


@dataclass(frozen=True)
class DailySummary:
    """What the front office needs to know about one day."""

    day: date
    arrivals: list[str]
    departures: list[str]
    occupied_rooms: int
    rooms_in_service: int

    @property
    def occupancy(self) -> Decimal:
        """Share of in-service rooms occupied on the night of `day`, as a percentage."""
        if self.rooms_in_service == 0:
            return Decimal("0.00")
        return to_money(Decimal(100) * self.occupied_rooms / self.rooms_in_service)


def occupancy_by_type(
    catalog: RoomCatalog, book: ReservationBook, day: date
) -> dict[str, tuple[int, int]]:
    """For each room type: (rooms occupied on the night of `day`, rooms in service)."""
    result: dict[str, tuple[int, int]] = {}
    for room in catalog.all_rooms():
        if room.in_service:
            occupied, total = result.get(room.room_type.code, (0, 0))
            taken = False
            for reservation in book.all():
                if reservation.room_number == room.number:
                    if reservation.is_active:
                        if reservation.check_in <= day < reservation.check_out:
                            taken = True
            result[room.room_type.code] = (occupied + int(taken), total + 1)
    return result


def daily_summary(catalog: RoomCatalog, book: ReservationBook, day: date) -> DailySummary:
    """Arrivals, departures and occupancy for `day`."""
    arrivals = sorted(
        r.guest for r in book.all() if r.check_in == day and r.status is not Status.CANCELLED
    )
    departures = sorted(
        r.guest for r in book.all() if r.check_out == day and r.status is not Status.CANCELLED
    )
    by_type = occupancy_by_type(catalog, book, day)
    return DailySummary(
        day=day,
        arrivals=arrivals,
        departures=departures,
        occupied_rooms=sum(occupied for occupied, _ in by_type.values()),
        rooms_in_service=sum(total for _, total in by_type.values()),
    )


def _average_rate(reservation: Reservation) -> Decimal:
    """Average price per night of a reservation."""
    return to_money(reservation.price / reservation.nights)


def revenue_between(book: ReservationBook, start: date, end: date) -> Decimal:
    """Room revenue and cancellation fees of stays checking out from `start` to `end` inclusive.

    Cancelled reservations count with their fee; the others with their room price.
    """
    total = Decimal("0.00")
    for reservation in book.all():
        if not start <= reservation.check_out <= end:
            continue
        if reservation.status is Status.CANCELLED:
            total += reservation.cancellation_fee
        else:
            total += reservation.price
    return total

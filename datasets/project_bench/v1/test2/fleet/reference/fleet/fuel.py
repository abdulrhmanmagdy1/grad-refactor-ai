"""Fuel purchases and fuel consumption."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date


@dataclass(frozen=True)
class FuelEntry:
    """One fill-up, with the odometer reading at the pump.

    ``entry_id`` is 0 until the entry is added to a :class:`FuelLog`.
    """

    vehicle_id: str
    day: date
    odometer_km: float
    liters: float
    price_per_liter: float
    full_tank: bool = True
    entry_id: int = 0

    @property
    def cost(self) -> float:
        """Amount paid for this fill-up, rounded to cents."""
        return round(self.liters * self.price_per_liter, 2)


class FuelLog:
    """Fuel purchases of the whole fleet, in the order they were made."""

    def __init__(self, entries: list[FuelEntry] | None = None) -> None:
        if entries is None:
            entries = []
        self._entries = entries
        self._next_id = max((e.entry_id for e in entries), default=0) + 1

    def add(self, entry: FuelEntry) -> FuelEntry:
        """Record a fill-up and return it numbered with its new entry id."""
        if entry.liters <= 0:
            raise ValueError("liters must be positive")
        if entry.price_per_liter < 0:
            raise ValueError("price per liter cannot be negative")
        numbered = replace(entry, entry_id=self._next_id)
        self._entries.append(numbered)
        self._next_id += 1
        return numbered

    def entries_for(
        self, vehicle_id: str, start: date | None = None, end: date | None = None
    ) -> list[FuelEntry]:
        """Fill-ups of one vehicle between ``start`` and ``end`` (inclusive), by odometer."""
        found = [
            e
            for e in self._entries
            if e.vehicle_id == vehicle_id
            and (start is None or e.day >= start)
            and (end is None or e.day <= end)
        ]
        return sorted(found, key=lambda e: e.odometer_km)

    def total_cost(
        self, vehicle_id: str, start: date | None = None, end: date | None = None
    ) -> float:
        """Money spent on fuel for one vehicle in the period."""
        return round(sum(e.cost for e in self.entries_for(vehicle_id, start, end)), 2)

    def total_liters(
        self, vehicle_id: str, start: date | None = None, end: date | None = None
    ) -> float:
        """Liters bought for one vehicle in the period."""
        return sum(e.liters for e in self.entries_for(vehicle_id, start, end))

    def all_entries(self) -> list[FuelEntry]:
        """Every fill-up, in the order they were recorded."""
        return list(self._entries)


def consumption_l_per_100km(entries: list[FuelEntry]) -> float | None:
    """Average consumption in liters per 100 km, measured full tank to full tank.

    The measured stretch runs from the first full-tank fill-up to the last one.
    The fuel bought at that first fill-up was burnt before the stretch began, so
    it is not counted; every liter bought after it, partial fill-ups included,
    up to and including the last full-tank fill-up, is. Returns ``None`` when
    there are fewer than two full-tank fill-ups or no distance between them.
    """
    ordered = sorted(entries, key=lambda e: e.odometer_km)
    full = [i for i, e in enumerate(ordered) if e.full_tank]
    if len(full) < 2:
        return None
    first, last = full[0], full[-1]
    distance = ordered[last].odometer_km - ordered[first].odometer_km
    if distance <= 0:
        return None
    liters = sum(e.liters for e in ordered[first + 1 : last + 1])
    return round(liters / distance * 100, 2)

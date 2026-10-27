"""Trips and the odometer readings they leave behind."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from fleet.models import Fleet


@dataclass(frozen=True)
class Trip:
    """One finished trip of one vehicle with one driver."""

    trip_id: int
    vehicle_id: str
    driver_id: str
    day: date
    start_km: float
    end_km: float
    purpose: str = ""

    @property
    def distance_km(self) -> float:
        """Kilometres driven on this trip."""
        return self.end_km - self.start_km


def _in_range(day: date, start: date | None, end: date | None) -> bool:
    """True when ``day`` lies between ``start`` and ``end``, both inclusive and optional."""
    if start is not None and day < start:
        return False
    return end is None or day <= end


class TripLog:
    """Records trips and keeps each vehicle's odometer up to date."""

    def __init__(self, fleet: Fleet) -> None:
        self._fleet = fleet
        self._trips: list[Trip] = []
        self._next_id = 1

    def record(
        self,
        vehicle_id: str,
        driver_id: str,
        day: date,
        end_km: float,
        purpose: str = "",
    ) -> Trip:
        """Record a finished trip that ended with the odometer at ``end_km``.

        The trip starts at the vehicle's current odometer reading. The vehicle
        must be in service, the driver's license must be valid on the day of the
        trip, and the odometer cannot go backwards.
        """
        vehicle = self._fleet.vehicle(vehicle_id)
        driver = self._fleet.driver(driver_id)
        if not vehicle.active:
            raise ValueError(f"vehicle {vehicle_id} is not in service")
        if day > driver.license_expires:
            raise ValueError(f"license of {driver.name} expired on {driver.license_expires}")
        if end_km < vehicle.odometer_km:
            raise ValueError("the odometer cannot go backwards")
        trip = Trip(self._next_id, vehicle_id, driver_id, day, vehicle.odometer_km, end_km, purpose)
        self._trips.append(trip)
        self._next_id += 1
        vehicle.odometer_km = end_km
        return trip

    def trips_for(
        self, vehicle_id: str, start: date | None = None, end: date | None = None
    ) -> list[Trip]:
        """Trips of one vehicle between ``start`` and ``end`` (inclusive), oldest first."""
        return [
            t for t in self._trips if t.vehicle_id == vehicle_id and _in_range(t.day, start, end)
        ]

    def distance_km(
        self, vehicle_id: str, start: date | None = None, end: date | None = None
    ) -> float:
        """Total kilometres one vehicle drove between ``start`` and ``end``."""
        return sum(t.distance_km for t in self.trips_for(vehicle_id, start, end))

    def distance_by_driver(
        self, start: date | None = None, end: date | None = None
    ) -> dict[str, float]:
        """Kilometres driven by each driver in the period, keyed by driver id."""
        totals: dict[str, float] = defaultdict(float)
        for trip in self._trips:
            if _in_range(trip.day, start, end):
                totals[trip.driver_id] += trip.distance_km
        return dict(totals)

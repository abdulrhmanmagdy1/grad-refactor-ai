"""Vehicles, drivers and the fleet that holds them."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Vehicle:
    """A vehicle in the fleet.

    ``odometer_km`` is the latest known odometer reading; recorded trips move it
    forward. ``in_service_since`` is the day the vehicle joined the fleet.
    """

    vehicle_id: str
    make: str
    model: str
    year: int
    in_service_since: date
    odometer_km: float = 0.0
    active: bool = True

    def label(self) -> str:
        """Return a short readable name such as ``"V12 Ford Transit (2019)"``."""
        return f"{self.vehicle_id} {self.make} {self.model} ({self.year})"


@dataclass
class Driver:
    """A person allowed to drive fleet vehicles."""

    driver_id: str
    name: str
    license_number: str
    license_expires: date

    def can_drive(self, day: date) -> bool:
        """Return True when the license is valid on ``day``.

        A license is valid up to and including its expiry date.
        """
        return day <= self.license_expires


@dataclass
class Fleet:
    """All vehicles and drivers, keyed by their ids."""

    vehicles: dict[str, Vehicle] = field(default_factory=dict)
    drivers: dict[str, Driver] = field(default_factory=dict)

    def add_vehicle(self, vehicle: Vehicle) -> None:
        """Register a vehicle; ids must be unique."""
        if vehicle.vehicle_id in self.vehicles:
            raise ValueError(f"vehicle {vehicle.vehicle_id} already exists")
        self.vehicles[vehicle.vehicle_id] = vehicle

    def add_driver(self, driver: Driver) -> None:
        """Register a driver; ids must be unique."""
        if driver.driver_id in self.drivers:
            raise ValueError(f"driver {driver.driver_id} already exists")
        self.drivers[driver.driver_id] = driver

    def vehicle(self, vehicle_id: str) -> Vehicle:
        """Return the vehicle with this id, or raise KeyError."""
        try:
            return self.vehicles[vehicle_id]
        except KeyError:
            raise KeyError(f"unknown vehicle {vehicle_id}") from None

    def driver(self, driver_id: str) -> Driver:
        """Return the driver with this id, or raise KeyError."""
        try:
            return self.drivers[driver_id]
        except KeyError:
            raise KeyError(f"unknown driver {driver_id}") from None

    def retire_vehicle(self, vehicle_id: str) -> None:
        """Take a vehicle out of service; its history is kept."""
        self.vehicle(vehicle_id).active = False

    def active_vehicles(self) -> list[Vehicle]:
        """Vehicles still in service, ordered by id."""
        return sorted(
            (v for v in self.vehicles.values() if v.active),
            key=lambda v: v.vehicle_id,
        )

    def expiring_licenses(self, today: date, within_days: int) -> list[Driver]:
        """Drivers whose license expires within ``within_days`` days of ``today``.

        Licenses that already expired are included, so nobody is missed.
        """
        return sorted(
            (d for d in self.drivers.values() if (d.license_expires - today).days <= within_days),
            key=lambda d: d.license_expires,
        )

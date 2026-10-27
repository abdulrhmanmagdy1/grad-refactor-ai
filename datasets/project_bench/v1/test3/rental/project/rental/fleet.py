"""Branches and vehicles: where each car is and whether it can be rented."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rental.rates import rate_for


class VehicleStatus(Enum):
    """Whether a vehicle can be handed to a customer."""

    AVAILABLE = "available"
    RENTED = "rented"
    MAINTENANCE = "maintenance"


@dataclass(frozen=True)
class Branch:
    """A rental counter, identified by a short code such as ``CAI-AIR``."""

    code: str
    name: str
    city: str


@dataclass
class Vehicle:
    """One car of the fleet and the branch it is parked at."""

    plate: str
    vehicle_class: str
    branch_code: str
    odometer: int
    status: VehicleStatus = VehicleStatus.AVAILABLE


class Fleet:
    """All branches and vehicles of the agency."""

    def __init__(self) -> None:
        self._branches: dict[str, Branch] = {}
        self._vehicles: dict[str, Vehicle] = {}

    def add_branch(self, branch: Branch) -> None:
        """Register a branch; branch codes are unique."""
        if branch.code in self._branches:
            raise ValueError(f"duplicate branch code: {branch.code}")
        self._branches[branch.code] = branch

    def branch(self, code: str) -> Branch:
        """Return the branch with ``code``; an unknown code raises ``KeyError``."""
        return self._branches[code]

    def add_vehicle(self, vehicle: Vehicle) -> None:
        """Register a vehicle of a known class at a known branch; plates are unique."""
        rate_for(vehicle.vehicle_class)
        if vehicle.branch_code not in self._branches:
            raise ValueError(f"unknown branch: {vehicle.branch_code}")
        if vehicle.plate in self._vehicles:
            raise ValueError(f"duplicate plate: {vehicle.plate}")
        self._vehicles[vehicle.plate] = vehicle

    def vehicle(self, plate: str) -> Vehicle:
        """Return the vehicle with ``plate``; an unknown plate raises ``KeyError``."""
        return self._vehicles[plate]

    def vehicles_at(self, branch_code: str) -> list[Vehicle]:
        """All vehicles parked at a branch, whatever their status, by plate."""
        found = [v for v in self._vehicles.values() if v.branch_code == branch_code]
        return sorted(found, key=lambda v: v.plate)

    def available(self, branch_code: str, vehicle_class: str) -> list[Vehicle]:
        """Available vehicles of one class at a branch, lowest odometer first."""
        found = [
            v
            for v in self.vehicles_at(branch_code)
            if v.vehicle_class == vehicle_class and v.status is VehicleStatus.AVAILABLE
        ]
        return sorted(found, key=lambda v: v.odometer)

    def check_out(self, plate: str) -> Vehicle:
        """Hand an available vehicle to a customer and return it."""
        vehicle = self.vehicle(plate)
        if vehicle.status is not VehicleStatus.AVAILABLE:
            raise ValueError(f"vehicle {plate} is {vehicle.status.value}")
        vehicle.status = VehicleStatus.RENTED
        return vehicle

    def check_in(self, plate: str, branch_code: str, odometer: int) -> Vehicle:
        """Take a rented vehicle back at ``branch_code`` with its new odometer reading.

        The vehicle becomes available at the branch where it was returned.
        """
        vehicle = self.vehicle(plate)
        if vehicle.status is not VehicleStatus.RENTED:
            raise ValueError(f"vehicle {plate} is not out on rent")
        if branch_code not in self._branches:
            raise ValueError(f"unknown branch: {branch_code}")
        if odometer < vehicle.odometer:
            raise ValueError("odometer reading is lower than at pick-up")
        vehicle.branch_code = branch_code
        vehicle.odometer = odometer
        vehicle.status = VehicleStatus.AVAILABLE
        return vehicle

    def retire_high_mileage(self, max_odometer: int) -> list[str]:
        """Remove available vehicles above ``max_odometer`` km and return their plates.

        Rented vehicles are kept until they come back.
        """
        retired: list[str] = []
        for plate, vehicle in list(self._vehicles.items()):
            if vehicle.status is VehicleStatus.AVAILABLE and vehicle.odometer > max_odometer:
                del self._vehicles[plate]
                retired.append(plate)
        return retired

"""Maintenance schedules by distance or by time, and service history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fleet.models import Vehicle


@dataclass(frozen=True)
class ServiceRule:
    """A recurring service, e.g. an oil change.

    The service is due every ``every_km`` kilometres or every ``every_days``
    days, whichever comes first. Either limit may be left out, but not both.
    """

    name: str
    every_km: float | None = None
    every_days: int | None = None

    def __post_init__(self) -> None:
        if self.every_km is None and self.every_days is None:
            raise ValueError(f"rule {self.name} needs a distance or a time limit")
        if self.every_km is not None and self.every_km <= 0:
            raise ValueError("every_km must be positive")
        if self.every_days is not None and self.every_days <= 0:
            raise ValueError("every_days must be positive")


@dataclass(frozen=True)
class ServiceRecord:
    """A service that was carried out."""

    vehicle_id: str
    rule_name: str
    day: date
    odometer_km: float
    cost: float


class MaintenancePlan:
    """Service rules for the fleet and the history of services done."""

    def __init__(self, rules: list[ServiceRule]) -> None:
        self._rules = {rule.name: rule for rule in rules}
        self._history: list[ServiceRecord] = []

    def record_service(
        self, vehicle_id: str, rule_name: str, day: date, odometer_km: float, cost: float
    ) -> ServiceRecord:
        """Record that a service was done; the rule must exist."""
        if rule_name not in self._rules:
            raise KeyError(f"unknown service rule {rule_name}")
        record = ServiceRecord(vehicle_id, rule_name, day, odometer_km, cost)
        self._history.append(record)
        return record

    def last_service(self, vehicle_id: str, rule_name: str) -> ServiceRecord | None:
        """The most recent service of this kind for the vehicle, if any."""
        done = [
            r for r in self._history if r.vehicle_id == vehicle_id and r.rule_name == rule_name
        ]
        return max(done, key=lambda r: r.day, default=None)

    @staticmethod
    def is_due(rule: ServiceRule, last: ServiceRecord, odometer_km: float, today: date) -> bool:
        """True when ``rule`` is due again since the ``last`` service."""
        km_due = rule.every_km is not None and odometer_km - last.odometer_km >= rule.every_km
        time_due = rule.every_days is not None and (today - last.day).days >= rule.every_days
        return km_due and time_due

    def due_services(self, vehicle: Vehicle, today: date) -> list[str]:
        """Names of the services due for ``vehicle`` today, in rule order.

        A vehicle that never had a service counts from the day it joined the
        fleet, at zero kilometres.
        """
        due = []
        for rule in self._rules.values():
            last = self.last_service(vehicle.vehicle_id, rule.name)
            if last is None:
                last = ServiceRecord(vehicle.vehicle_id, rule.name, vehicle.in_service_since, 0.0, 0.0)
            if self.is_due(rule, last, vehicle.odometer_km, today):
                due.append(rule.name)
        return due

    def service_cost(
        self, vehicle_id: str, start: date | None = None, end: date | None = None
    ) -> float:
        """Money spent on services of one vehicle between ``start`` and ``end`` (inclusive)."""
        return round(
            sum(
                r.cost
                for r in self._history
                if r.vehicle_id == vehicle_id
                and (start is None or r.day >= start)
                and (end is None or r.day <= end)
            ),
            2,
        )

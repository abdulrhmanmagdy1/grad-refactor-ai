"""Cost report: fuel and maintenance spending per vehicle for a period."""

from __future__ import annotations

from datetime import date

from fleet.fuel import FuelLog
from fleet.maintenance import MaintenancePlan
from fleet.models import Fleet
from fleet.trips import TripLog


def cost_report(
    fleet: Fleet,
    trips: TripLog,
    fuel: FuelLog,
    maintenance: MaintenancePlan,
    start: date,
    end: date,
) -> str:
    """Plain-text cost report for every vehicle in service, from ``start`` to ``end``.

    One line per vehicle with the distance driven, fuel cost, service cost, total
    cost and cost per kilometre ("-" when the vehicle did not move), sorted by
    total cost, highest first. A fleet total line closes the report.
    """
    if end < start:
        raise ValueError("the report period ends before it starts")
    rows = []
    for vehicle in fleet.active_vehicles():
        distance = trips.distance_km(vehicle.vehicle_id, start, end)
        fuel_cost = fuel.total_cost(vehicle.vehicle_id, start, end)
        service_cost = maintenance.service_cost(vehicle.vehicle_id, start, end)
        total = round(fuel_cost + service_cost, 2)
        if distance > 0:
            per_km = f"{total / distance:.3f}"
        else:
            per_km = "-"
        rows.append(
            {
                "label": vehicle.label(),
                "distance": distance,
                "fuel": fuel_cost,
                "service": service_cost,
                "total": total,
                "per_km": per_km,
            }
        )
    rows.sort(key=lambda row: row["total"], reverse=True)
    width = max([len(row["label"]) for row in rows] + [len("Vehicle")])
    lines = [
        f"Fleet costs {start.isoformat()} to {end.isoformat()}",
        "",
        f"{'Vehicle':<{width}}  {'km':>9}  {'fuel':>10}  {'service':>10}"
        f"  {'total':>10}  {'per km':>7}",
    ]
    for row in rows:
        lines.append(
            f"{row['label']:<{width}}  {row['distance']:>9.1f}  {row['fuel']:>10.2f}"
            f"  {row['service']:>10.2f}  {row['total']:>10.2f}  {row['per_km']:>7}"
        )
    fleet_distance = sum(row["distance"] for row in rows)
    fleet_fuel = round(sum(row["fuel"] for row in rows), 2)
    fleet_service = round(sum(row["service"] for row in rows), 2)
    fleet_total = round(fleet_fuel + fleet_service, 2)
    if fleet_distance > 0:
        fleet_per_km = f"{fleet_total / fleet_distance:.3f}"
    else:
        fleet_per_km = "-"
    lines.append("")
    lines.append(
        f"{'Total':<{width}}  {fleet_distance:>9.1f}  {fleet_fuel:>10.2f}"
        f"  {fleet_service:>10.2f}  {fleet_total:>10.2f}  {fleet_per_km:>7}"
    )
    return "\n".join(lines)


def driver_ranking(trips: TripLog, fleet: Fleet, start: date, end: date) -> list[tuple[str, float]]:
    """Drivers by kilometres driven in the period, most first, as ``(name, km)`` pairs."""
    totals = trips.distance_by_driver(start, end)
    ranked = [(fleet.driver(driver_id).name, km) for driver_id, km in totals.items()]
    return sorted(ranked, key=lambda pair: (-pair[1], pair[0]))

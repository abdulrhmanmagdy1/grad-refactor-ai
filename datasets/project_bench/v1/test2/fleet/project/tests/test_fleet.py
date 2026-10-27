from datetime import date

import pytest

from fleet.fuel import FuelEntry, FuelLog, consumption_l_per_100km
from fleet.maintenance import MaintenancePlan, ServiceRule
from fleet.models import Driver, Fleet, Vehicle
from fleet.report import cost_report, driver_ranking
from fleet.storage import load_fleet, receipt_fingerprint, save_fleet, save_receipt
from fleet.trips import TripLog


def make_fleet() -> Fleet:
    fleet = Fleet()
    fleet.add_vehicle(Vehicle("V1", "Ford", "Transit", 2019, date(2024, 1, 1), 10_000.0))
    fleet.add_vehicle(Vehicle("V2", "Toyota", "Hilux", 2021, date(2024, 1, 1), 5_000.0))
    fleet.add_driver(Driver("D1", "Sara", "L-100", date(2027, 6, 30)))
    fleet.add_driver(Driver("D2", "Omar", "L-200", date(2026, 3, 31)))
    return fleet


def test_duplicate_vehicle_rejected():
    fleet = make_fleet()
    with pytest.raises(ValueError):
        fleet.add_vehicle(Vehicle("V1", "Ford", "Focus", 2020, date(2024, 1, 1)))


def test_retired_vehicles_are_not_active():
    fleet = make_fleet()
    fleet.retire_vehicle("V2")
    assert [v.vehicle_id for v in fleet.active_vehicles()] == ["V1"]


def test_expiring_licenses():
    fleet = make_fleet()
    soon = fleet.expiring_licenses(date(2026, 3, 1), within_days=60)
    assert [d.driver_id for d in soon] == ["D2"]


def test_trip_moves_the_odometer():
    fleet = make_fleet()
    log = TripLog(fleet)
    trip = log.record("V1", "D1", date(2026, 1, 5), 10_250.0, "delivery")
    assert trip.distance_km == 250.0
    assert fleet.vehicle("V1").odometer_km == 10_250.0


def test_odometer_cannot_go_backwards():
    fleet = make_fleet()
    log = TripLog(fleet)
    with pytest.raises(ValueError):
        log.record("V1", "D1", date(2026, 1, 5), 9_000.0)


def test_expired_license_cannot_drive():
    fleet = make_fleet()
    log = TripLog(fleet)
    with pytest.raises(ValueError):
        log.record("V1", "D2", date(2026, 4, 2), 10_100.0)


def test_distance_by_driver():
    fleet = make_fleet()
    log = TripLog(fleet)
    log.record("V1", "D1", date(2026, 1, 5), 10_100.0)
    log.record("V2", "D1", date(2026, 1, 6), 5_050.0)
    log.record("V1", "D2", date(2026, 1, 7), 10_300.0)
    assert log.distance_by_driver() == {"D1": 150.0, "D2": 200.0}
    assert driver_ranking(log, fleet, date(2026, 1, 1), date(2026, 1, 31)) == [
        ("Omar", 200.0),
        ("Sara", 150.0),
    ]


def test_fuel_totals():
    log = FuelLog()
    log.add(FuelEntry("F1", date(2026, 2, 1), 1_000.0, 40.0, 1.5))
    log.add(FuelEntry("F1", date(2026, 2, 9), 1_400.0, 30.0, 1.6))
    assert log.total_cost("F1") == 108.0
    assert log.total_liters("F1", start=date(2026, 2, 5)) == 30.0


def test_fuel_rejects_non_positive_liters():
    log = FuelLog([])
    with pytest.raises(ValueError):
        log.add(FuelEntry("F2", date(2026, 2, 1), 1_000.0, 0.0, 1.5))


def test_consumption_needs_two_full_tanks():
    log = FuelLog([])
    log.add(FuelEntry("F3", date(2026, 2, 1), 1_000.0, 40.0, 1.5))
    assert consumption_l_per_100km(log.entries_for("F3")) is None


def test_service_due_when_both_limits_passed():
    fleet = make_fleet()
    plan = MaintenancePlan([ServiceRule("oil", every_km=10_000, every_days=365)])
    plan.record_service("V1", "oil", date(2024, 6, 1), 0.0, 120.0)
    assert plan.due_services(fleet.vehicle("V1"), date(2025, 7, 1)) == ["oil"]


def test_service_not_due_before_limits():
    fleet = make_fleet()
    plan = MaintenancePlan([ServiceRule("oil", every_km=10_000, every_days=365)])
    plan.record_service("V1", "oil", date(2025, 6, 1), 9_000.0, 120.0)
    assert plan.due_services(fleet.vehicle("V1"), date(2025, 7, 1)) == []


def test_rule_needs_a_limit():
    with pytest.raises(ValueError):
        ServiceRule("wash")


def test_cost_report_lists_vehicles_by_total():
    fleet = make_fleet()
    trips = TripLog(fleet)
    trips.record("V1", "D1", date(2026, 3, 2), 10_200.0)
    fuel = FuelLog([])
    fuel.add(FuelEntry("V1", date(2026, 3, 2), 10_200.0, 20.0, 1.5))
    plan = MaintenancePlan([ServiceRule("oil", every_km=10_000)])
    plan.record_service("V2", "oil", date(2026, 3, 3), 5_000.0, 80.0)
    text = cost_report(fleet, trips, fuel, plan, date(2026, 3, 1), date(2026, 3, 31))
    lines = text.splitlines()
    assert lines[3].startswith("V2 Toyota Hilux")
    assert lines[4].startswith("V1 Ford Transit")
    assert lines[4].endswith("0.150")
    assert lines[-1].startswith("Total")


def test_fleet_round_trip(tmp_path):
    fleet = make_fleet()
    path = tmp_path / "fleet.json"
    save_fleet(fleet, path)
    loaded = load_fleet(path)
    assert loaded.vehicle("V2") == fleet.vehicle("V2")
    assert loaded.driver("D1") == fleet.driver("D1")


def test_receipt_saved_under_entry(tmp_path):
    path = save_receipt(tmp_path, 7, "pump.pdf", b"%PDF")
    assert path == tmp_path / "receipts" / "7" / "pump.pdf"
    assert path.read_bytes() == b"%PDF"


def test_receipt_type_checked(tmp_path):
    with pytest.raises(ValueError):
        save_receipt(tmp_path, 7, "notes.txt", b"x")


def test_fingerprint_is_stable():
    assert receipt_fingerprint(b"abc") == receipt_fingerprint(b"abc")
    assert receipt_fingerprint(b"abc") != receipt_fingerprint(b"abd")

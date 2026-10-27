import logging
from datetime import date

import pytest

from fleet.fuel import FuelEntry, FuelLog, consumption_l_per_100km
from fleet.maintenance import MaintenancePlan, ServiceRule
from fleet.models import Driver, Fleet, Vehicle
from fleet.storage import load_fleet, receipt_fingerprint, save_receipt
from fleet.trips import TripLog


def _vehicle(odometer: float) -> Vehicle:
    return Vehicle("H1", "Ford", "Transit", 2019, date(2024, 1, 1), odometer)


def test_B1_service_due_on_distance_alone():
    plan = MaintenancePlan([ServiceRule("oil", every_km=10_000, every_days=365)])
    plan.record_service("H1", "oil", date(2026, 1, 1), 20_000.0, 90.0)
    assert plan.due_services(_vehicle(31_000.0), date(2026, 2, 1)) == ["oil"]


def test_B1_service_due_on_time_alone():
    plan = MaintenancePlan([ServiceRule("oil", every_km=10_000, every_days=365)])
    plan.record_service("H1", "oil", date(2024, 1, 1), 20_000.0, 90.0)
    assert plan.due_services(_vehicle(21_000.0), date(2025, 6, 1)) == ["oil"]


def test_B1_rule_with_only_a_time_limit():
    plan = MaintenancePlan([ServiceRule("inspection", every_days=180)])
    assert plan.due_services(_vehicle(100.0), date(2024, 12, 1)) == ["inspection"]


def test_B2_new_logs_start_empty():
    first = FuelLog()
    first.add(FuelEntry("H1", date(2026, 2, 1), 1_000.0, 40.0, 1.5))
    second = FuelLog()
    assert second.all_entries() == []
    assert second.total_cost("H1") == 0


def test_B3_first_full_tank_not_counted():
    entries = [
        FuelEntry("H1", date(2026, 2, 1), 1_000.0, 40.0, 1.5, True, entry_id=1),
        FuelEntry("H1", date(2026, 2, 4), 1_300.0, 10.0, 1.5, False, entry_id=2),
        FuelEntry("H1", date(2026, 2, 7), 1_500.0, 20.0, 1.5, True, entry_id=3),
    ]
    assert consumption_l_per_100km(entries) == pytest.approx(6.0)


def test_S1_receipt_cannot_escape_the_data_folder(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    try:
        save_receipt(root, 7, "../../../escape.pdf", b"%PDF")
    except (ValueError, OSError):
        pass
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(root in p.parents for p in written)


def test_keep_plain_receipt_name(tmp_path):
    path = save_receipt(tmp_path, 3, "Pump receipt.jpg", b"img")
    assert path.read_bytes() == b"img"
    assert path.parent == tmp_path / "receipts" / "3"


def test_keep_consumption_needs_distance():
    entries = [
        FuelEntry("H2", date(2026, 2, 1), 2_000.0, 45.0, 1.5, True, entry_id=1),
        FuelEntry("H2", date(2026, 2, 1), 2_000.0, 5.0, 1.5, True, entry_id=2),
    ]
    assert consumption_l_per_100km(entries) is None


def test_keep_log_built_from_entries_continues_ids():
    log = FuelLog([FuelEntry("H3", date(2026, 1, 1), 500.0, 10.0, 1.0, entry_id=4)])
    entry = log.add(FuelEntry("H3", date(2026, 1, 2), 600.0, 10.0, 1.0))
    assert entry.entry_id == 5
    assert len(log.all_entries()) == 2


def test_keep_service_not_due_within_both_limits():
    plan = MaintenancePlan([ServiceRule("oil", every_km=10_000, every_days=365)])
    plan.record_service("H1", "oil", date(2026, 1, 1), 20_000.0, 90.0)
    assert plan.due_services(_vehicle(25_000.0), date(2026, 6, 1)) == []


def test_keep_license_valid_on_expiry_day():
    fleet = Fleet()
    fleet.add_vehicle(_vehicle(0.0))
    fleet.add_driver(Driver("D9", "Lina", "L-9", date(2026, 5, 31)))
    trip = TripLog(fleet).record("H1", "D9", date(2026, 5, 31), 80.0)
    assert trip.distance_km == 80.0
    assert fleet.driver("D9").can_drive(date(2026, 5, 31))
    assert not fleet.driver("D9").can_drive(date(2026, 6, 1))


def test_keep_fingerprint_is_md5_hex():
    assert receipt_fingerprint(b"") == "d41d8cd98f00b204e9800998ecf8427e"


def test_keep_load_logs_and_reraises(tmp_path, caplog):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        load_fleet(path)
    assert "could not load the fleet" in caplog.text

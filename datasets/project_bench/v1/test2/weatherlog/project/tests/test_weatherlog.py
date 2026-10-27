from datetime import date, datetime

import pytest

from weatherlog.aggregate import summarize_all, summarize_day
from weatherlog.alerts import AlertEngine, frost_rule, gale_rule, heavy_rain_days
from weatherlog.export import changed_exports, export_daily_csv, export_station_csv, file_checksum
from weatherlog.ingest import Ingestor
from weatherlog.models import Reading, Station, StationRegistry
from weatherlog.units import celsius_to_fahrenheit, fahrenheit_to_celsius, to_metric
from weatherlog.validation import validate


def reading(hour: int, temp: float = 10.0, *, station: str = "s1", wind: float = 2.0, rain: float = 0.0) -> Reading:
    return Reading(station, datetime(2026, 3, 1, hour), temp, 60.0, wind, rain)


def registry() -> StationRegistry:
    reg = StationRegistry()
    reg.register(Station("s1", "Harbour"))
    reg.register(Station("s2", "Ridge", units="imperial"))
    return reg


def test_conversions_round_trip():
    assert fahrenheit_to_celsius(212.0) == pytest.approx(100.0)
    assert celsius_to_fahrenheit(fahrenheit_to_celsius(50.0)) == pytest.approx(50.0)
    assert to_metric(1.0, 2.0, 3.0, "metric") == (1.0, 2.0, 3.0)


def test_validate_rejects_impossible_temperature():
    bad = Reading("s1", datetime(2026, 3, 1), 75.0, 50.0, 1.0, 0.0)
    issues = validate(bad)
    assert [issue.field for issue in issues] == ["temperature_c"]


def test_ingest_converts_imperial_payloads():
    ingestor = Ingestor(registry())
    payload = {"station_id": "s2", "taken_at": "2026-03-01T06:00:00", "temperature": 50, "humidity": 70, "wind": 10, "rain": 0.5}
    stored = ingestor.ingest(payload)
    assert stored is not None
    assert stored.temperature_c == pytest.approx(10.0)
    assert stored.rain_mm == pytest.approx(12.7)


def test_ingest_batch_counts_stored_readings():
    ingestor = Ingestor(registry())
    batch = {
        "station_id": "s1",
        "readings": [
            {"taken_at": "2026-03-01T06:00:00", "temperature": 4, "humidity": 80, "wind": 3},
            {"taken_at": "2026-03-01T07:00:00", "temperature": 5, "humidity": 80, "wind": 3},
        ],
    }
    assert ingestor.ingest_batch(batch) == 2
    assert len(ingestor.accepted) == 2


def test_daily_summary():
    readings = [reading(6, 2.0, rain=1.5), reading(12, 8.0, wind=10.0), reading(18, 5.0, rain=0.5)]
    summary = summarize_day(readings, "s1", date(2026, 3, 1))
    assert summary is not None
    assert (summary.min_temp_c, summary.max_temp_c, summary.mean_temp_c) == (2.0, 8.0, 5.0)
    assert summary.rain_total_mm == 2.0
    assert summary.max_wind_kmh == 36.0
    assert len(summarize_all(readings + [reading(6, station="s2")])) == 2


def test_frost_alert_fires_once():
    engine = AlertEngine([frost_rule()])
    alerts = engine.process([reading(1, 3.0), reading(2, -1.0)])
    assert [a.rule for a in alerts] == ["frost"]


def test_gale_and_rain_alerts():
    assert len(AlertEngine([gale_rule(60.0)]).process([reading(1, wind=20.0)])) == 1
    readings = [reading(1, rain=20.0), reading(2, rain=15.0)]
    assert [a.rule for a in heavy_rain_days(readings, 30.0)] == ["heavy-rain"]


def test_exports(tmp_path):
    path = export_station_csv(tmp_path / "out", "s1", [reading(7), reading(6)])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("station_id,taken_at")
    assert lines[1].split(",")[1] == "2026-03-01T06:00:00"
    daily = export_daily_csv(tmp_path / "out", summarize_all([reading(6)]))
    assert daily.exists()
    known = {"s1.csv": file_checksum(path)}
    assert changed_exports(tmp_path / "out", known) == ["daily.csv"]


def test_registry_prune():
    reg = registry()
    reg.deactivate("s2")
    assert reg.active_ids() == ["s1"]
    assert reg.prune_inactive() == ["s2"]
    assert len(reg) == 1

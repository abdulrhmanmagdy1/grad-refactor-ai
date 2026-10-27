from datetime import date, datetime
from pathlib import Path

import pytest

from weatherlog.aggregate import summarize_day
from weatherlog.alerts import AlertEngine, ThresholdRule, frost_rule
from weatherlog.export import export_station_csv, file_checksum
from weatherlog.ingest import Ingestor
from weatherlog.models import Reading, Station, StationRegistry
from weatherlog.validation import check_range, validate


def make(hour: int, temp: float = 10.0, *, station: str = "s1", humidity: float = 60.0) -> Reading:
    return Reading(station, datetime(2026, 3, 1, hour), temp, humidity, 2.0, 0.0)


def registry() -> StationRegistry:
    reg = StationRegistry()
    reg.register(Station("s1", "Harbour"))
    return reg


def bad_payload() -> dict:
    return {"station_id": "s1", "taken_at": "2026-03-01T06:00:00", "temperature": 99, "humidity": 50, "wind": 1}


def test_B1_upper_limits_are_accepted():
    assert validate(make(6, humidity=100.0)) == []
    assert check_range("rain_mm", 500.0) is None
    assert check_range("temperature_c", 60.0) is None


def test_keep_values_past_the_limits_are_refused():
    assert check_range("humidity_pct", 100.5) is not None
    assert check_range("wind_ms", -0.1) is not None
    assert check_range("rain_mm", 0.0) is None


def test_B2_run_restarts_after_a_reading_within_the_limit():
    rule = ThresholdRule("heat", "temperature_c", 30.0, consecutive=3)
    engine = AlertEngine([rule])
    alerts = engine.process([make(1, 31.0), make(2, 32.0), make(3, 25.0), make(4, 33.0)])
    assert alerts == []


def test_keep_rule_fires_once_per_run_and_per_station():
    rule = ThresholdRule("heat", "temperature_c", 30.0, consecutive=2)
    readings = [make(1, 31.0), make(2, 31.0), make(3, 31.0), make(4, 31.0, station="s2"), make(5, 31.0, station="s2")]
    alerts = AlertEngine([rule]).process(readings)
    assert [(a.station_id, a.when.hour) for a in alerts] == [("s1", 2), ("s2", 5)]
    assert len(AlertEngine([frost_rule()]).process([make(1, -2.0)])) == 1


def test_B3_ingestors_keep_their_own_rejections():
    first = Ingestor(registry())
    first.ingest(bad_payload())
    second = Ingestor(registry())
    assert len(first.rejected) == 1
    assert second.rejected == []


def test_keep_ingest_rejects_unknown_and_inactive_stations():
    reg = registry()
    reg.register(Station("s9", "Old", active=False))
    ingestor = Ingestor(reg)
    before = len(ingestor.rejected)
    payload = bad_payload() | {"temperature": 10}
    assert ingestor.ingest(payload | {"station_id": "nope"}) is None
    assert ingestor.ingest(payload | {"station_id": "s9"}) is None
    assert ingestor.ingest(payload) is not None
    assert len(ingestor.rejected) == before + 2


def test_S1_station_id_cannot_escape_the_export_folder(tmp_path):
    folder = tmp_path / "a" / "b" / "out"
    readings = [make(6, station="../escaped")]
    try:
        export_station_csv(folder, "../escaped", readings)
    except Exception:
        pass
    outside = [p for p in tmp_path.rglob("*.csv") if folder not in p.parents]
    assert outside == []


def test_keep_normal_station_export(tmp_path):
    path = export_station_csv(tmp_path / "out", "s1", [make(6)])
    assert path.parent == tmp_path / "out"
    assert path.name == "s1.csv"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_keep_checksum_is_md5_of_the_file(tmp_path):
    import hashlib

    path = Path(tmp_path / "x.csv")
    path.write_bytes(b"a,b\n1,2\n")
    assert file_checksum(path) == hashlib.md5(b"a,b\n1,2\n").hexdigest()


def test_keep_prune_while_iterating():
    reg = registry()
    reg.register(Station("s2", "Ridge"))
    reg.register(Station("s3", "Lake"))
    reg.deactivate("s1")
    reg.deactivate("s3")
    assert sorted(reg.prune_inactive()) == ["s1", "s3"]
    assert reg.active_ids() == ["s2"]


def test_keep_daily_summary_wind_in_kmh():
    summary = summarize_day([make(6), make(7, 4.0)], "s1", date(2026, 3, 1))
    assert summary is not None
    assert summary.max_wind_kmh == pytest.approx(7.2)
    assert summary.mean_temp_c == 7.0

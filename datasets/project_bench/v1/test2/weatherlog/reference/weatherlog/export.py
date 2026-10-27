"""CSV exports of readings and daily summaries into an export folder."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Iterable

from weatherlog.aggregate import DailySummary
from weatherlog.models import Reading

READING_COLUMNS = ["station_id", "taken_at", "temperature_c", "humidity_pct", "wind_kmh", "rain_mm"]
SUMMARY_COLUMNS = [
    "station_id",
    "day",
    "count",
    "min_temp_c",
    "max_temp_c",
    "mean_temp_c",
    "rain_total_mm",
    "max_wind_kmh",
]


def reading_row(reading: Reading) -> list[str]:
    """The CSV row for a reading; wind is written in km/h with 1 decimal."""
    return [
        reading.station_id,
        reading.taken_at.isoformat(),
        f"{reading.temperature_c:.2f}",
        f"{reading.humidity_pct:.1f}",
        f"{reading.wind_ms * 3.6:.1f}",
        f"{reading.rain_mm:.2f}",
    ]


def export_station_csv(folder: Path, station_id: str, readings: Iterable[Reading]) -> Path:
    """Write the readings of one station to <station_id>.csv in folder.

    The folder is created when missing. Rows are ordered by time. Returns the
    path of the written file.
    """
    if not station_id or Path(station_id).name != station_id or station_id in (".", ".."):
        raise ValueError(f"invalid station id {station_id!r}")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{station_id}.csv"
    rows = sorted((r for r in readings if r.station_id == station_id), key=lambda r: r.taken_at)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(READING_COLUMNS)
        writer.writerows(reading_row(r) for r in rows)
    return target


def export_daily_csv(folder: Path, summaries: Iterable[DailySummary], name: str = "daily.csv") -> Path:
    """Write daily summaries to folder/name and return the path."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(SUMMARY_COLUMNS)
        for s in summaries:
            writer.writerow(
                [
                    s.station_id,
                    s.day.isoformat(),
                    s.count,
                    s.min_temp_c,
                    s.max_temp_c,
                    s.mean_temp_c,
                    s.rain_total_mm,
                    s.max_wind_kmh,
                ]
            )
    return target


def file_checksum(path: Path) -> str:
    """Hex digest of a file's bytes, used to skip re-uploading unchanged exports."""
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def changed_exports(folder: Path, known: dict[str, str]) -> list[str]:
    """Names of the CSV files in folder whose checksum differs from known[name]."""
    return [path.name for path in sorted(folder.glob("*.csv")) if known.get(path.name) != file_checksum(path)]

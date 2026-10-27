"""Daily aggregates per station: temperature range and mean, rain and wind."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import fmean
from typing import Iterable

from weatherlog import alerts
from weatherlog.models import Reading


@dataclass(frozen=True)
class DailySummary:
    """What one station measured during one calendar day."""

    station_id: str
    day: date
    count: int
    min_temp_c: float
    max_temp_c: float
    mean_temp_c: float
    rain_total_mm: float
    max_wind_kmh: float
    frost_readings: int


def readings_for_day(readings: Iterable[Reading], station_id: str, day: date) -> list[Reading]:
    """The readings of station_id taken on day, oldest first."""
    selected = [r for r in readings if r.station_id == station_id and r.taken_at.date() == day]
    return sorted(selected, key=lambda r: r.taken_at)


def summarize_day(readings: Iterable[Reading], station_id: str, day: date) -> DailySummary | None:
    """Summarize one station-day, or return None when it has no readings.

    Temperatures and rain are rounded to 2 decimals, wind to 1 decimal in km/h.
    Rain is the sum of the per-reading amounts.
    """
    selected = readings_for_day(readings, station_id, day)
    if not selected:
        return None
    temps = [r.temperature_c for r in selected]
    return DailySummary(
        station_id=station_id,
        day=day,
        count=len(selected),
        min_temp_c=round(min(temps), 2),
        max_temp_c=round(max(temps), 2),
        mean_temp_c=round(fmean(temps), 2),
        rain_total_mm=round(sum(r.rain_mm for r in selected), 2),
        max_wind_kmh=round(max(r.wind_ms for r in selected) * 3.6, 1),
        frost_readings=sum(1 for t in temps if t <= alerts.FROST_LIMIT_C),
    )


def summarize_all(readings: Iterable[Reading]) -> list[DailySummary]:
    """One summary per station-day present in readings, ordered by station then day."""
    readings = list(readings)
    keys: dict[str, set[date]] = defaultdict(set)
    for reading in readings:
        keys[reading.station_id].add(reading.taken_at.date())
    summaries: list[DailySummary] = []
    for station_id in sorted(keys):
        for day in sorted(keys[station_id]):
            summary = summarize_day(readings, station_id, day)
            if summary is not None:
                summaries.append(summary)
    return summaries

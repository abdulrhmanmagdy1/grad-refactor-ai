"""Alert rules evaluated over the stream of readings and over daily summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from weatherlog import aggregate
from weatherlog.models import Reading

FROST_LIMIT_C = 0.0


@dataclass(frozen=True)
class Alert:
    """A rule that fired for a station."""

    station_id: str
    rule: str
    when: datetime | date
    message: str


class ThresholdRule:
    """Fire when a field is past a limit for `consecutive` readings in a row.

    With above=True the limit is passed when the value is greater than it,
    otherwise when it is smaller. Each station has its own run of readings.
    The rule fires once, on the reading that completes the run; a reading back
    within the limit ends the run.
    """

    def __init__(self, name: str, field: str, limit: float, *, above: bool = True, consecutive: int = 1) -> None:
        if consecutive < 1:
            raise ValueError("consecutive must be at least 1")
        self.name = name
        self.field = field
        self.limit = limit
        self.above = above
        self.consecutive = consecutive
        self._runs: dict[str, int] = {}

    def _passed(self, value: float) -> bool:
        return value > self.limit if self.above else value < self.limit

    def observe(self, reading: Reading) -> Alert | None:
        """Feed the next reading of a station; return an alert when the rule fires."""
        value = getattr(reading, self.field)
        if not self._passed(value):
            return None
        run = self._runs.get(reading.station_id, 0) + 1
        self._runs[reading.station_id] = run
        if run != self.consecutive:
            return None
        message = f"{self.field}={value} past {self.limit} for {run} reading(s)"
        return Alert(reading.station_id, self.name, reading.taken_at, message)


def frost_rule(consecutive: int = 1) -> ThresholdRule:
    """Alert when the temperature drops below FROST_LIMIT_C."""
    return ThresholdRule("frost", "temperature_c", FROST_LIMIT_C, above=False, consecutive=consecutive)


def gale_rule(limit_kmh: float, consecutive: int = 1) -> ThresholdRule:
    """Alert when the wind is above limit_kmh (km/h)."""
    return ThresholdRule("gale", "wind_ms", limit_kmh / 3.6, consecutive=consecutive)


class AlertEngine:
    """Runs a fixed set of rules over readings in time order."""

    def __init__(self, rules: Iterable[ThresholdRule]) -> None:
        self.rules = list(rules)

    def process(self, readings: Iterable[Reading]) -> list[Alert]:
        """Evaluate every rule on every reading, oldest reading first."""
        fired: list[Alert] = []
        for reading in sorted(readings, key=lambda r: r.taken_at):
            for rule in self.rules:
                alert = rule.observe(reading)
                if alert is not None:
                    fired.append(alert)
        return fired


def heavy_rain_days(readings: Iterable[Reading], limit_mm: float) -> list[Alert]:
    """One alert for every station-day whose rain total reaches limit_mm."""
    fired: list[Alert] = []
    for summary in aggregate.summarize_all(readings):
        if summary.rain_total_mm >= limit_mm:
            message = f"{summary.rain_total_mm} mm of rain (limit {limit_mm})"
            fired.append(Alert(summary.station_id, "heavy-rain", summary.day, message))
    return fired

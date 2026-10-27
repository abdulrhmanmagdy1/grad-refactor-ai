"""Core data types: stations, the station registry and readings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

UNIT_SYSTEMS = ("metric", "imperial")


@dataclass(frozen=True)
class Reading:
    """One observation from a station, stored in metric units.

    temperature_c is in degrees Celsius, humidity_pct in percent, wind_ms in
    metres per second and rain_mm is the rain that fell since the station's
    previous reading.
    """

    station_id: str
    taken_at: datetime
    temperature_c: float
    humidity_pct: float
    wind_ms: float
    rain_mm: float


@dataclass
class Station:
    """A weather station that is allowed to send readings.

    units says how the station sends its values: "metric" stations send
    Celsius, m/s and mm, "imperial" stations send Fahrenheit, mph and inches.
    """

    station_id: str
    name: str
    units: str = "metric"
    active: bool = True

    def __post_init__(self) -> None:
        if self.units not in UNIT_SYSTEMS:
            raise ValueError(f"unknown unit system {self.units!r}")


class StationRegistry:
    """The set of known stations, keyed by station id."""

    def __init__(self) -> None:
        self._stations: dict[str, Station] = {}

    def register(self, station: Station) -> None:
        """Add a station; registering the same id twice is an error."""
        if station.station_id in self._stations:
            raise ValueError(f"station {station.station_id} is already registered")
        self._stations[station.station_id] = station

    def get(self, station_id: str) -> Station:
        """Return the station with this id or raise KeyError."""
        try:
            return self._stations[station_id]
        except KeyError:
            raise KeyError(f"unknown station {station_id!r}") from None

    def deactivate(self, station_id: str) -> None:
        """Stop accepting readings from a station without forgetting it."""
        self.get(station_id).active = False

    def active_ids(self) -> list[str]:
        """Ids of the stations that currently accept readings, sorted."""
        return sorted(s.station_id for s in self._stations.values() if s.active)

    def prune_inactive(self) -> list[str]:
        """Forget every deactivated station and return the removed ids."""
        removed: list[str] = []
        for station_id in list(self._stations):
            if not self._stations[station_id].active:
                del self._stations[station_id]
                removed.append(station_id)
        return removed

    def __len__(self) -> int:
        return len(self._stations)

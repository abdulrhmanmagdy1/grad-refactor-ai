"""Turn raw payloads sent by stations into validated metric readings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from weatherlog.models import Reading, Station, StationRegistry
from weatherlog.units import to_metric
from weatherlog.validation import validate


@dataclass(frozen=True)
class Rejection:
    """A payload that was not stored, with the reason."""

    payload: dict[str, Any]
    reason: str


def to_reading(payload: dict[str, Any], station: Station) -> Reading:
    """Build a metric Reading from a payload sent by station.

    A payload has the keys taken_at (ISO 8601), temperature, humidity, wind and
    optionally rain (0 when missing), in the station's unit system.
    """
    temperature, wind, rain = to_metric(
        float(payload["temperature"]),
        float(payload["wind"]),
        float(payload.get("rain", 0.0)),
        station.units,
    )
    return Reading(
        station_id=station.station_id,
        taken_at=datetime.fromisoformat(payload["taken_at"]),
        temperature_c=temperature,
        humidity_pct=float(payload["humidity"]),
        wind_ms=wind,
        rain_mm=rain,
    )


class Ingestor:
    """Accepts payloads for the stations in a registry.

    accepted holds the readings this ingestor stored and rejected the payloads
    it refused, in arrival order.
    """

    def __init__(self, registry: StationRegistry, rejected: list[Rejection] = []) -> None:
        self.registry = registry
        self.accepted: list[Reading] = []
        self.rejected = rejected

    def _reject(self, payload: dict[str, Any], reason: str) -> None:
        self.rejected.append(Rejection(dict(payload), reason))

    def ingest(self, payload: dict[str, Any], now: datetime | None = None) -> Reading | None:
        """Convert and validate one payload.

        Returns the stored reading, or None when the payload was malformed, came
        from an unknown or inactive station, or failed validation.
        """
        try:
            station = self.registry.get(str(payload["station_id"]))
            reading = to_reading(payload, station)
        except (KeyError, TypeError, ValueError) as exc:
            self._reject(payload, f"malformed payload: {exc}")
            return None
        if not station.active:
            self._reject(payload, f"station {station.station_id} is inactive")
            return None
        issues = validate(reading, now)
        if issues:
            self._reject(payload, "; ".join(issue.message for issue in issues))
            return None
        self.accepted.append(reading)
        return reading

    def ingest_batch(self, batch: dict[str, Any], now: datetime | None = None) -> int:
        """Ingest a batch upload and return how many readings were stored.

        A batch is {"station_id": ..., "readings": [payload, ...]}. Payloads may
        leave out station_id; one that names a different station is rejected.
        """
        stored = 0
        if isinstance(batch, dict):
            station_id = batch.get("station_id")
            if station_id is not None:
                for item in batch.get("readings", []):
                    if isinstance(item, dict):
                        payload = {"station_id": station_id, **item}
                        if payload["station_id"] == station_id:
                            if self.ingest(payload, now) is not None:
                                stored += 1
                        else:
                            self._reject(payload, "station id does not match the batch")
                    else:
                        self.rejected.append(Rejection({"item": item}, "not an object"))
        return stored

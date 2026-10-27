"""Plausibility checks applied to every reading before it is stored."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from weatherlog.models import Reading

# Lowest and highest plausible value for each measured field, both inclusive.
LIMITS: dict[str, tuple[float, float]] = {
    "temperature_c": (-80.0, 60.0),
    "humidity_pct": (0.0, 100.0),
    "wind_ms": (0.0, 115.0),
    "rain_mm": (0.0, 500.0),
}

MAX_CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class ValidationIssue:
    """Why a reading was refused."""

    field: str
    value: object
    message: str


def check_range(field: str, value: float) -> ValidationIssue | None:
    """Return an issue when value lies outside the inclusive LIMITS of field."""
    low, high = LIMITS[field]
    if low <= value < high:
        return None
    return ValidationIssue(field, value, f"{field}={value} outside [{low}, {high}]")


def check_timestamp(reading: Reading, now: datetime) -> ValidationIssue | None:
    """Refuse readings stamped further in the future than MAX_CLOCK_SKEW."""
    if reading.taken_at - now > MAX_CLOCK_SKEW:
        return ValidationIssue("taken_at", reading.taken_at, "reading is from the future")
    return None


def validate(reading: Reading, now: datetime | None = None) -> list[ValidationIssue]:
    """Return every problem found in reading; an empty list means it is valid."""
    issues: list[ValidationIssue] = []
    for field in LIMITS:
        issue = check_range(field, getattr(reading, field))
        if issue is not None:
            issues.append(issue)
    if now is not None:
        late = check_timestamp(reading, now)
        if late is not None:
            issues.append(late)
    return issues

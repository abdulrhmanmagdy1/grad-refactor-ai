"""Spans of time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Interval:
    """The time from ``start`` up to, but not including, ``end``."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"an interval must end after it starts: {self.start} to {self.end}")

    @property
    def duration(self) -> timedelta:
        """Length of the interval."""
        return self.end - self.start

    def overlaps(self, other: Interval) -> bool:
        """Return True when the two intervals share some time.

        Intervals that only touch, one ending when the other starts, do not overlap: a
        meeting from 9:00 to 10:00 and one from 10:00 to 11:00 can use the same room.
        """
        return self.start < other.end and other.start < self.end


def format_span(interval: Interval) -> str:
    """Format an interval as ``09:00-10:30``."""
    return f"{interval.start:%H:%M}-{interval.end:%H:%M}"

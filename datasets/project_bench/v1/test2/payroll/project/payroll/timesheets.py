"""Timesheets and the overtime rule."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

OVERTIME_THRESHOLD = Decimal(40)
OVERTIME_MULTIPLIER = Decimal("1.5")
MAX_HOURS_PER_DAY = Decimal(24)


@dataclass(frozen=True)
class TimeEntry:
    """Hours worked on one day."""

    day: date
    hours: Decimal


class Timesheet:
    """Hours worked by one employee in one calendar month."""

    def __init__(self, employee_id: str, year: int, month: int) -> None:
        if not 1 <= month <= 12:
            raise ValueError("month must be between 1 and 12")
        self.employee_id = employee_id
        self.year = year
        self.month = month
        self._entries: list[TimeEntry] = []

    @property
    def entries(self) -> list[TimeEntry]:
        """The entries, in the order they were recorded."""
        return list(self._entries)

    def add(self, day: date, hours: Decimal) -> None:
        """Record hours worked on a day of this month; a day holds at most 24 hours."""
        if (day.year, day.month) != (self.year, self.month):
            raise ValueError(f"{day} is not in {self.year}-{self.month:02d}")
        if hours <= 0:
            raise ValueError("hours must be positive")
        if self.hours_on(day) + hours > MAX_HOURS_PER_DAY:
            raise ValueError(f"more than 24 hours on {day}")
        self._entries.append(TimeEntry(day, hours))

    def hours_on(self, day: date) -> Decimal:
        """Total hours recorded on one day."""
        return sum((entry.hours for entry in self._entries if entry.day == day), Decimal(0))

    def total_hours(self) -> Decimal:
        """Total hours recorded in the month."""
        return sum((entry.hours for entry in self._entries), Decimal(0))

    def hours_by_week(self) -> dict[tuple[int, int], Decimal]:
        """Hours per ISO week (year, week number), for the days of this month."""
        weeks: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
        for entry in self._entries:
            iso = entry.day.isocalendar()
            weeks[(iso.year, iso.week)] += entry.hours
        return dict(weeks)


def split_overtime(timesheet: Timesheet) -> tuple[Decimal, Decimal]:
    """Return (regular hours, overtime hours) of the month.

    In each ISO week, the hours above 40 are overtime; the rest are regular.
    """
    regular = Decimal(0)
    overtime = Decimal(0)
    for hours in timesheet.hours_by_week().values():
        extra = max(hours - OVERTIME_THRESHOLD, Decimal(0))
        overtime += extra
        regular += hours - extra
    return regular, overtime

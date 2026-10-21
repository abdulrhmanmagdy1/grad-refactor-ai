"""Recurring meetings: on which days a series falls."""

from __future__ import annotations

import calendar
import itertools
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

MAX_OCCURRENCES = 366
MONTHS_PER_YEAR = 12
WEEKEND = frozenset({5, 6})  # Saturday and Sunday, as numbered by date.weekday()


class Frequency(StrEnum):
    """The unit a series repeats in."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True)
class Recurrence:
    """How a meeting repeats.

    ``interval`` is the step between meetings, in days, weeks or months. The series
    ends after ``count`` meetings (the first one included) or with the last meeting on
    or before ``until``; at least one of the two must be given.
    """

    frequency: Frequency
    interval: int = 1
    count: int | None = None
    until: date | None = None

    def __post_init__(self) -> None:
        if self.interval < 1:
            raise ValueError("interval must be at least 1")
        if self.count is None and self.until is None:
            raise ValueError("a series needs a count or an end date")
        if self.count is not None and self.count < 1:
            raise ValueError("count must be at least 1")


def _candidate(first: datetime, rule: Recurrence, n: int) -> datetime | None:
    """Return the ``n``-th candidate start of the series, 0 being ``first`` itself.

    Monthly series keep the day of the month of ``first``; None means that the month
    has no such day.
    """
    if rule.frequency is Frequency.DAILY:
        return first + timedelta(days=n * rule.interval)
    if rule.frequency is Frequency.WEEKLY:
        return first + timedelta(weeks=n * rule.interval)
    months = first.month - 1 + n * rule.interval
    year, month = first.year + months // MONTHS_PER_YEAR, months % MONTHS_PER_YEAR + 1
    if first.day > calendar.monthrange(year, month)[1]:
        return None
    return first.replace(year=year, month=month)


def occurrences(first: datetime, rule: Recurrence) -> list[datetime]:
    """Return the start of every meeting of the series, ``first`` included.

    Daily series skip Saturdays and Sundays. Monthly series skip the months that lack
    the day of ``first`` (a series on the 31st has no meeting in April). Skipped days
    do not count towards ``count``. At most MAX_OCCURRENCES starts are returned.
    """
    starts: list[datetime] = []
    for n in itertools.count():
        start = _candidate(first, rule, n)
        if start is None:
            continue
        if rule.frequency is Frequency.DAILY and start.weekday() in WEEKEND:
            continue
        if rule.until is not None and start.date() > rule.until:
            break
        starts.append(start)
        if len(starts) in (rule.count, MAX_OCCURRENCES):
            break
    return starts

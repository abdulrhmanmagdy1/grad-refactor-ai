"""Opening hours of restaurants."""

from __future__ import annotations

from datetime import datetime

from delivery.models import OpeningHours, Restaurant


def is_open(restaurant: Restaurant, at: datetime) -> bool:
    """Return True when the restaurant takes orders at the moment ``at``.

    Each window starts on its weekday at ``opens`` (inclusive) and ends at
    ``closes`` (exclusive). A window whose closing time is earlier than its
    opening time runs past midnight, so it also covers the early hours of
    the following weekday.
    """
    moment = at.time()
    for window in restaurant.hours:
        if window.weekday != at.weekday():
            continue
        if window.opens <= moment < window.closes:
            return True
    return False


def windows_on(restaurant: Restaurant, weekday: int) -> list[OpeningHours]:
    """Return the windows that start on ``weekday``, earliest first."""
    found = [window for window in restaurant.hours if window.weekday == weekday]
    return sorted(found, key=lambda window: window.opens)


def describe_day(restaurant: Restaurant, weekday: int) -> str:
    """Return the day's hours as text, such as ``"11:00-15:00, 18:00-23:00"``."""
    windows = windows_on(restaurant, weekday)
    if not windows:
        return "closed"
    parts = [f"{w.opens:%H:%M}-{w.closes:%H:%M}" for w in windows]
    return ", ".join(parts)

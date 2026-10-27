from datetime import datetime, time

from delivery.hours import describe_day, is_open
from delivery.models import Location, OpeningHours, Restaurant


def make_restaurant() -> Restaurant:
    hours = [
        OpeningHours(0, time(18, 0), time(22, 0)),
        OpeningHours(0, time(11, 0), time(15, 0)),
    ]
    return Restaurant("r9", "Noodle Bar", Location(0, 0), hours=hours)


def test_open_inside_window() -> None:
    # 2026-10-26 is a Monday.
    assert is_open(make_restaurant(), datetime(2026, 10, 26, 12, 30))


def test_opening_time_is_inclusive_closing_exclusive() -> None:
    restaurant = make_restaurant()
    assert is_open(restaurant, datetime(2026, 10, 26, 11, 0))
    assert not is_open(restaurant, datetime(2026, 10, 26, 15, 0))


def test_closed_on_other_days() -> None:
    assert not is_open(make_restaurant(), datetime(2026, 10, 27, 12, 30))


def test_describe_day() -> None:
    restaurant = make_restaurant()
    assert describe_day(restaurant, 0) == "11:00-15:00, 18:00-22:00"
    assert describe_day(restaurant, 3) == "closed"

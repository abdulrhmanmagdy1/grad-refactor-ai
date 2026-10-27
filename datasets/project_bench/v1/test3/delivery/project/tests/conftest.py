from datetime import time
from decimal import Decimal

import pytest

from delivery.models import Location, MenuItem, MenuOption, OpeningHours, Restaurant


@pytest.fixture
def pizzeria() -> Restaurant:
    margherita = MenuItem(
        "m1",
        "Margherita",
        Decimal("8.50"),
        options={
            "cheese": MenuOption("cheese", Decimal("1.20")),
            "olives": MenuOption("olives", Decimal("0.80")),
        },
    )
    lemonade = MenuItem("d1", "Lemonade", Decimal("2.40"))
    hours = [OpeningHours(day, time(11, 0), time(22, 0)) for day in range(7)]
    return Restaurant(
        "r1",
        "Luigi's",
        Location(0.0, 0.0),
        hours=hours,
        menu={"m1": margherita, "d1": lemonade},
    )

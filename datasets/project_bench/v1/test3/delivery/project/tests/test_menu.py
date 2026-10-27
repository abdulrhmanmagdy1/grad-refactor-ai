from decimal import Decimal

import pytest

from delivery.menu import MenuError, check_lines, menu_checksum, subtotal
from delivery.models import OrderLine, Restaurant


def test_subtotal_with_options(pizzeria: Restaurant) -> None:
    lines = [OrderLine("m1", 2, ["cheese"]), OrderLine("d1", 1)]
    assert subtotal(pizzeria, lines) == Decimal("21.80")


def test_check_lines_reports_each_problem(pizzeria: Restaurant) -> None:
    pizzeria.menu["d1"].available = False
    lines = [
        OrderLine("x9", 1),
        OrderLine("m1", 1, ["anchovies"]),
        OrderLine("m1", 0),
        OrderLine("d1", 1),
    ]
    problems = check_lines(pizzeria, lines)
    assert len(problems) == 4


def test_subtotal_rejects_bad_lines(pizzeria: Restaurant) -> None:
    with pytest.raises(MenuError):
        subtotal(pizzeria, [OrderLine("m1", 1, ["anchovies"])])


def test_checksum_follows_price_changes(pizzeria: Restaurant) -> None:
    before = menu_checksum(pizzeria)
    assert menu_checksum(pizzeria) == before
    pizzeria.menu["m1"].price = Decimal("8.90")
    assert menu_checksum(pizzeria) != before

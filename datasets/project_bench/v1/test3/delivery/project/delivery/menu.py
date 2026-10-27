"""Menu lookups, order line checks and line pricing."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from delivery.models import MenuItem, OrderLine, Restaurant


class MenuError(ValueError):
    """Raised when order lines do not match the restaurant's menu."""


def check_lines(restaurant: Restaurant, lines: list[OrderLine]) -> list[str]:
    """Return the problems with ``lines``; an empty list means they are valid.

    Every line must name an available item on the menu, have a positive
    quantity and only choose options the item offers.
    """
    problems: list[str] = []
    for line in lines:
        if line.item_id in restaurant.menu:
            item = restaurant.menu[line.item_id]
            if item.available:
                if line.quantity > 0:
                    for option in line.options:
                        if option not in item.options:
                            problems.append(f"{item.name}: unknown option {option!r}")
                else:
                    problems.append(f"{item.name}: quantity must be positive")
            else:
                problems.append(f"{item.name} is not available")
        else:
            problems.append(f"unknown item {line.item_id!r}")
    return problems


def unit_price(item: MenuItem, option_names: list[str]) -> Decimal:
    """Return the price of one item with the chosen options added."""
    extras = sum((item.options[name].price for name in option_names), Decimal("0"))
    return item.price + extras


def line_price(restaurant: Restaurant, line: OrderLine) -> Decimal:
    """Return the price of a whole line: unit price times quantity."""
    item = restaurant.menu[line.item_id]
    return unit_price(item, line.options) * line.quantity


def subtotal(restaurant: Restaurant, lines: list[OrderLine]) -> Decimal:
    """Return the food subtotal of valid lines; raise MenuError otherwise."""
    problems = check_lines(restaurant, lines)
    if problems:
        raise MenuError("; ".join(problems))
    return sum((line_price(restaurant, line) for line in lines), Decimal("0.00"))


def menu_checksum(restaurant: Restaurant) -> str:
    """Return a short fingerprint of the menu so clients can cache it.

    It changes whenever an item, a price, an option or availability changes.
    """
    digest = hashlib.sha256()
    for item_id in sorted(restaurant.menu):
        item = restaurant.menu[item_id]
        digest.update(f"{item_id}|{item.name}|{item.price}|{item.available}".encode())
        for name in sorted(item.options):
            digest.update(f"|{name}={item.options[name].price}".encode())
        digest.update(b"\n")
    return digest.hexdigest()[:16]

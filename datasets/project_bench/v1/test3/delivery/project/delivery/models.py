"""Core data types shared by the delivery service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal


@dataclass(frozen=True)
class Location:
    """A point on the map in decimal degrees."""

    lat: float
    lon: float


@dataclass(frozen=True)
class OpeningHours:
    """One opening window starting on a weekday (0 is Monday).

    ``closes`` may be earlier than ``opens``: the window then runs past
    midnight into the next day, as for a kitchen open from 18:00 to 02:00.
    """

    weekday: int
    opens: time
    closes: time


@dataclass(frozen=True)
class MenuOption:
    """An extra a customer can add to a dish, such as extra cheese."""

    name: str
    price: Decimal


@dataclass
class MenuItem:
    """A dish on a menu together with the options that may be added to it."""

    item_id: str
    name: str
    price: Decimal
    options: dict[str, MenuOption] = field(default_factory=dict)
    available: bool = True


@dataclass
class Restaurant:
    """A restaurant with its location, weekly opening hours and menu."""

    restaurant_id: str
    name: str
    location: Location
    hours: list[OpeningHours] = field(default_factory=list)
    menu: dict[str, MenuItem] = field(default_factory=dict)
    prep_minutes: int = 15


@dataclass
class OrderLine:
    """A quantity of one menu item with the names of the chosen options."""

    item_id: str
    quantity: int
    options: list[str] = field(default_factory=list)


@dataclass
class Courier:
    """A courier who can carry one order at a time."""

    courier_id: str
    name: str
    location: Location
    vehicle: str = "bike"
    available: bool = True


@dataclass
class Order:
    """A placed order with its money amounts in the restaurant's currency."""

    order_id: str
    restaurant_id: str
    customer_location: Location
    lines: list[OrderLine]
    subtotal: Decimal
    delivery_fee: Decimal
    tip: Decimal = Decimal("0.00")
    courier_id: str | None = None
    tracking_token: str = ""
    eta_minutes: int | None = None
    status: str = "placed"

    @property
    def total(self) -> Decimal:
        """What the customer pays: food, delivery fee and tip."""
        return self.subtotal + self.delivery_fee + self.tip

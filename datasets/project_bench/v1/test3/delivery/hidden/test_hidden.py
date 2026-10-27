import random
from datetime import datetime, time
from decimal import Decimal

from delivery.couriers import CourierPool
from delivery.fees import band_fee
from delivery.hours import is_open
from delivery.menu import menu_checksum
from delivery.models import (
    Courier,
    Location,
    MenuItem,
    OpeningHours,
    Order,
    OrderLine,
    Restaurant,
)
from delivery.orders import OrderService, new_tracking_token


def _late_kitchen() -> Restaurant:
    # Friday (weekday 4) from 18:00 to 02:00 on Saturday.
    return Restaurant(
        "r2",
        "Late Kitchen",
        Location(0.0, 0.0),
        hours=[OpeningHours(4, time(18, 0), time(2, 0))],
        menu={"b1": MenuItem("b1", "Burger", Decimal("9.00"))},
    )


def _order(customer: Location) -> Order:
    return Order("O1", "r2", customer, [OrderLine("b1", 1)], Decimal("9.00"), Decimal("2.90"))


def test_B1_fee_band_limit_is_inclusive() -> None:
    assert band_fee(Decimal("2")) == Decimal("1.50")
    assert band_fee(Decimal("5")) == Decimal("2.90")
    assert band_fee(Decimal("8")) == Decimal("4.50")


def test_keep_fee_bands_between_limits() -> None:
    assert band_fee(Decimal("0")) == Decimal("1.50")
    assert band_fee(Decimal("2.1")) == Decimal("2.90")
    assert band_fee(Decimal("5.1")) == Decimal("4.50")


def test_B2_overnight_window_open_before_and_after_midnight() -> None:
    kitchen = _late_kitchen()
    # 2026-10-30 is a Friday, 2026-10-31 a Saturday.
    assert is_open(kitchen, datetime(2026, 10, 30, 23, 30))
    assert is_open(kitchen, datetime(2026, 10, 31, 1, 30))
    assert not is_open(kitchen, datetime(2026, 10, 31, 2, 0))
    assert not is_open(kitchen, datetime(2026, 10, 30, 17, 59))
    assert not is_open(kitchen, datetime(2026, 10, 30, 1, 30))


def test_keep_daytime_window_bounds() -> None:
    restaurant = Restaurant(
        "r3", "Cafe", Location(0, 0), hours=[OpeningHours(2, time(8, 0), time(16, 0))]
    )
    assert is_open(restaurant, datetime(2026, 10, 28, 8, 0))
    assert is_open(restaurant, datetime(2026, 10, 28, 15, 59))
    assert not is_open(restaurant, datetime(2026, 10, 28, 16, 0))
    assert not is_open(restaurant, datetime(2026, 10, 29, 9, 0))


def test_B3_courier_closest_to_restaurant_is_assigned() -> None:
    restaurant = _late_kitchen()
    customer = Location(0.04, 0.0)
    pool = CourierPool()
    pool.add(Courier("c1", "Near customer", Location(0.04, 0.001)))
    pool.add(Courier("c2", "Near restaurant", Location(0.001, 0.0)))
    chosen = pool.assign(_order(customer), restaurant)
    assert chosen is not None and chosen.courier_id == "c2"


def test_keep_assignment_ties_go_to_lower_id() -> None:
    restaurant = _late_kitchen()
    pool = CourierPool()
    pool.add(Courier("c7", "A", Location(0.0, 0.0)))
    pool.add(Courier("c3", "B", Location(0.0, 0.0)))
    first = pool.assign(_order(Location(0.01, 0.0)), restaurant)
    assert first is not None and first.courier_id == "c3"
    assert pool.courier_for("O1") == "c3"


def test_S1_tracking_tokens_do_not_follow_the_random_seed() -> None:
    random.seed(1234)
    first = new_tracking_token()
    random.seed(1234)
    second = new_tracking_token()
    assert isinstance(first, str) and len(first) >= 16
    assert first != second


def test_keep_tracking_tokens_are_unique_per_order() -> None:
    restaurant = Restaurant(
        "r1",
        "Diner",
        Location(0.0, 0.0),
        hours=[OpeningHours(d, time(0, 0), time(23, 59)) for d in range(7)],
        menu={"b1": MenuItem("b1", "Burger", Decimal("13.00"))},
    )
    service = OrderService([restaurant], CourierPool())
    at = datetime(2026, 10, 26, 16, 0)
    tokens = {
        service.place("r1", [OrderLine("b1", 1)], Location(0.01, 0.0), at).tracking_token
        for _ in range(20)
    }
    assert len(tokens) == 20
    for token in tokens:
        assert service.track(token) is not None
    assert service.track("not-a-token") is None


def test_keep_release_frees_only_delivered_couriers() -> None:
    restaurant = _late_kitchen()
    pool = CourierPool()
    for n in range(4):
        pool.add(Courier(f"c{n}", f"C{n}", Location(0.0, 0.0)))
    for n in range(4):
        order = Order(f"O{n}", "r2", Location(0.01, 0), [], Decimal("9"), Decimal("1.5"))
        pool.assign(order, restaurant)
    assert pool.available() == []
    assert pool.release_finished({"O0", "O2", "O9"}) == 2
    assert sorted(c.courier_id for c in pool.available()) == ["c0", "c2"]
    assert pool.courier_for("O1") is not None
    assert pool.courier_for("O0") is None


def test_keep_checksum_tracks_options_and_availability() -> None:
    restaurant = _late_kitchen()
    base = menu_checksum(restaurant)
    assert len(base) == 16
    restaurant.menu["b1"].available = False
    assert menu_checksum(restaurant) != base
    restaurant.menu["b1"].available = True
    assert menu_checksum(restaurant) == base

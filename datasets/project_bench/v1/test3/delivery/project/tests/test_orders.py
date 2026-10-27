from datetime import datetime
from decimal import Decimal

import pytest

from delivery.couriers import CourierPool
from delivery.estimates import estimate_minutes, is_peak
from delivery.models import Courier, Location, OrderLine, Restaurant
from delivery.orders import OrderError, OrderService, tip_amount

CUSTOMER = Location(0.03, 0.0)
AFTERNOON = datetime(2026, 10, 26, 16, 0)


def make_service(restaurant: Restaurant) -> tuple[OrderService, CourierPool]:
    pool = CourierPool()
    pool.add(Courier("c1", "Sara", Location(0.0, 0.0)))
    return OrderService([restaurant], pool), pool


def test_tip_rounds_half_up() -> None:
    assert tip_amount(Decimal("10.10"), Decimal("15")) == Decimal("1.52")
    with pytest.raises(OrderError):
        tip_amount(Decimal("10"), Decimal("-5"))


def test_place_order(pizzeria: Restaurant) -> None:
    service, _ = make_service(pizzeria)
    order = service.place("r1", [OrderLine("m1", 2, ["cheese"])], CUSTOMER, AFTERNOON, Decimal("10"))
    assert order.subtotal == Decimal("19.40")
    assert order.delivery_fee == Decimal("2.90")
    assert order.tip == Decimal("1.94")
    assert order.total == Decimal("24.24")
    assert order.courier_id == "c1"
    assert order.eta_minutes == 32
    assert service.track(order.tracking_token) is order


def test_closed_restaurant_rejects_orders(pizzeria: Restaurant) -> None:
    service, _ = make_service(pizzeria)
    with pytest.raises(OrderError):
        service.place("r1", [OrderLine("d1", 1)], CUSTOMER, datetime(2026, 10, 26, 23, 0))


def test_second_order_waits_for_a_courier(pizzeria: Restaurant) -> None:
    service, _ = make_service(pizzeria)
    first = service.place("r1", [OrderLine("m1", 2)], CUSTOMER, AFTERNOON)
    second = service.place("r1", [OrderLine("m1", 2)], CUSTOMER, AFTERNOON)
    assert second.courier_id is None and second.eta_minutes is None
    assert service.mark_delivered({first.order_id}) == 1
    assert service.revenue() == first.total


def test_estimate_is_longer_at_peak(pizzeria: Restaurant) -> None:
    courier = Courier("c2", "Omar", Location(0.0, 0.0), vehicle="car")
    rush = datetime(2026, 10, 26, 19, 30)
    assert is_peak(rush) and not is_peak(AFTERNOON)
    assert estimate_minutes(pizzeria, courier, CUSTOMER, rush) > estimate_minutes(
        pizzeria, courier, CUSTOMER, AFTERNOON
    )

"""Courier pool and assignment of couriers to orders."""

from __future__ import annotations

from delivery import estimates
from delivery.geo import distance_km
from delivery.models import Courier, Order, Restaurant

VEHICLE_SPEED_KMH: dict[str, float] = {"bike": 15.0, "scooter": 25.0, "car": 30.0}


class CourierPool:
    """The couriers on shift and the orders they are carrying."""

    def __init__(self) -> None:
        self._couriers: dict[str, Courier] = {}
        self._assignments: dict[str, str] = {}

    def add(self, courier: Courier) -> None:
        """Put a courier on shift."""
        if courier.vehicle not in VEHICLE_SPEED_KMH:
            raise ValueError(f"unknown vehicle {courier.vehicle!r}")
        self._couriers[courier.courier_id] = courier

    def get(self, courier_id: str) -> Courier:
        """Return the courier with this id."""
        return self._couriers[courier_id]

    def available(self) -> list[Courier]:
        """Return the couriers who are not carrying an order."""
        return [c for c in self._couriers.values() if c.available]

    def courier_for(self, order_id: str) -> str | None:
        """Return the id of the courier carrying ``order_id``, if any."""
        return self._assignments.get(order_id)

    def assign(self, order: Order, restaurant: Restaurant) -> Courier | None:
        """Assign the free courier closest to the restaurant to ``order``.

        The courier has to pick the food up first, so the distance that
        matters is from the courier to the restaurant. Ties go to the lower
        courier id. Returns None when no courier is free.
        """
        if order.restaurant_id != restaurant.restaurant_id:
            raise ValueError(f"order {order.order_id} is not from {restaurant.name}")
        free = self.available()
        if not free:
            return None
        best = min(
            free,
            key=lambda c: (distance_km(c.location, order.customer_location), c.courier_id),
        )
        best.available = False
        self._assignments[order.order_id] = best.courier_id
        order.courier_id = best.courier_id
        return best

    def pickup_minutes(self, courier: Courier, restaurant: Restaurant) -> float:
        """Return how long the courier needs to reach the restaurant."""
        km = distance_km(courier.location, restaurant.location)
        return estimates.travel_minutes(km, courier.vehicle)

    def release_finished(self, delivered: set[str]) -> int:
        """Free the couriers whose orders were delivered; return how many."""
        released = 0
        for order_id in list(self._assignments):
            if order_id in delivered:
                courier_id = self._assignments.pop(order_id)
                self._couriers[courier_id].available = True
                released += 1
        return released

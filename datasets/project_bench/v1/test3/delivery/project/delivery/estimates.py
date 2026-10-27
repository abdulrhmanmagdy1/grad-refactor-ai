"""Delivery time estimates."""

from __future__ import annotations

import math
from datetime import datetime

from delivery import couriers
from delivery.geo import distance_km
from delivery.models import Courier, Location, Restaurant

PEAK_WINDOWS: tuple[tuple[int, int], ...] = ((12, 14), (19, 21))
PEAK_PREP_FACTOR = 1.5
HANDOVER_MINUTES = 3


def travel_minutes(km: float, vehicle: str) -> float:
    """Return the minutes needed to ride ``km`` kilometres on ``vehicle``."""
    speed = couriers.VEHICLE_SPEED_KMH[vehicle]
    return km / speed * 60


def is_peak(at: datetime) -> bool:
    """Return True during the lunch and dinner rush (start hour inclusive)."""
    return any(start <= at.hour < end for start, end in PEAK_WINDOWS)


def prep_minutes(restaurant: Restaurant, at: datetime) -> float:
    """Return the kitchen's preparation time, longer during the rush."""
    minutes = float(restaurant.prep_minutes)
    if is_peak(at):
        minutes *= PEAK_PREP_FACTOR
    return minutes


def estimate_minutes(
    restaurant: Restaurant, courier: Courier, customer_at: Location, at: datetime
) -> int:
    """Return the minutes until the order reaches the customer, rounded up.

    The courier rides to the restaurant while the food is prepared, so the
    pickup happens after the longer of the two. Then comes the ride to the
    customer and a fixed handover time.
    """
    to_restaurant = travel_minutes(distance_km(courier.location, restaurant.location), courier.vehicle)
    to_customer = travel_minutes(distance_km(restaurant.location, customer_at), courier.vehicle)
    pickup = max(prep_minutes(restaurant, at), to_restaurant)
    return math.ceil(pickup + to_customer + HANDOVER_MINUTES)

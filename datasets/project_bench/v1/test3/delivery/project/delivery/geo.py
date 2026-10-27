"""Distances between map points."""

from __future__ import annotations

import math

from delivery.models import Location

EARTH_RADIUS_KM = 6371.0


def distance_km(a: Location, b: Location) -> float:
    """Return the great-circle distance between two points in kilometres."""
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))

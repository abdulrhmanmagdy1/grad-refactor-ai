"""Conversions between the imperial units some stations send and metric units."""

from __future__ import annotations

MPH_TO_MS = 0.44704
INCH_TO_MM = 25.4


def fahrenheit_to_celsius(value: float) -> float:
    """Convert degrees Fahrenheit to degrees Celsius."""
    return (value - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(value: float) -> float:
    """Convert degrees Celsius to degrees Fahrenheit."""
    return value * 9.0 / 5.0 + 32.0


def mph_to_ms(value: float) -> float:
    """Convert miles per hour to metres per second."""
    return value * MPH_TO_MS


def inches_to_mm(value: float) -> float:
    """Convert inches of rain to millimetres."""
    return value * INCH_TO_MM


def to_metric(temperature: float, wind: float, rain: float, units: str) -> tuple[float, float, float]:
    """Return (celsius, m/s, mm) for values sent in the given unit system."""
    if units == "metric":
        return temperature, wind, rain
    if units == "imperial":
        return fahrenheit_to_celsius(temperature), mph_to_ms(wind), inches_to_mm(rain)
    raise ValueError(f"unknown unit system {units!r}")

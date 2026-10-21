"""Units of measure and conversions between them."""

from __future__ import annotations

from fractions import Fraction

# Canonical unit -> (dimension, size in the base unit of that dimension).
UNITS: dict[str, tuple[str, float]] = {
    "g": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "ml": ("volume", 1.0),
    "l": ("volume", 1000.0),
    "tsp": ("volume", 5.0),
    "tbsp": ("volume", 15.0),
    "cup": ("volume", 240.0),
    "piece": ("count", 1.0),
}

BASE_UNITS = {"mass": "g", "volume": "ml", "count": "piece"}


def normalize_unit(text: str) -> str:
    """The canonical unit for a spelling such as "Grams", "cups" or "tbsp.".

    An empty unit means pieces. Unknown units raise ValueError.
    """
    word = text.strip().lower().rstrip(".")
    if word in ("", "piece", "pieces", "pc", "pcs"):
        return "piece"
    elif word in ("g", "gr", "gram", "grams"):
        return "g"
    elif word in ("kg", "kilo", "kilos", "kilogram", "kilograms"):
        return "kg"
    elif word in ("ml", "millilitre", "millilitres", "milliliter", "milliliters"):
        return "ml"
    elif word in ("l", "litre", "litres", "liter", "liters"):
        return "l"
    elif word in ("tsp", "teaspoon", "teaspoons"):
        return "tsp"
    elif word in ("tbsp", "tablespoon", "tablespoons"):
        return "tbsp"
    elif word in ("cup", "cups"):
        return "cup"
    else:
        raise ValueError(f"unknown unit {text!r}")


def to_base(amount: float, unit: str) -> tuple[float, str]:
    """The amount in the base unit of its dimension (g, ml or piece), and the dimension."""
    dimension, size = UNITS[normalize_unit(unit)]
    return amount * size, dimension


def convert(amount: float, unit: str, target: str) -> float:
    """Convert an amount from one unit to another of the same dimension.

    Mass, volume and pieces cannot be converted into each other (that would need the
    density or the weight of a piece), so mixing dimensions raises ValueError, as do
    unknown units.
    """
    dimension, size = UNITS[normalize_unit(unit)]
    target_dimension, target_size = UNITS[normalize_unit(target)]
    if dimension != target_dimension:
        raise ValueError(f"cannot convert {dimension} to {target_dimension}")
    return amount * size / target_size


def readable(amount: float, dimension: str) -> tuple[float, str]:
    """A base amount in the unit a shopper reads best: kg from 1000 g, l from 1000 ml."""
    base = BASE_UNITS[dimension]
    if dimension == "mass" and amount >= 1000:
        return round(convert(amount, base, "kg"), 3), "kg"
    if dimension == "volume" and amount >= 1000:
        return round(convert(amount, base, "l"), 3), "l"
    return round(amount, 2), base


def _fraction_text(amount: float) -> str:
    """Kitchen-style text for an amount: 1.5 is "1 1/2" and 0.25 is "1/4"."""
    whole = int(amount)
    rest = Fraction(amount - whole).limit_denominator(8)
    if rest == 0:
        return str(whole)
    if whole == 0:
        return str(rest)
    return f"{whole} {rest}"

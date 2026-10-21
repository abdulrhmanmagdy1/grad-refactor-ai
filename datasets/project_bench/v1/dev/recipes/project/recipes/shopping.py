"""The merged shopping list for a meal plan."""

from __future__ import annotations

from dataclasses import dataclass

from recipes.loader import LOADED
from recipes.scaling import scale
from recipes.units import readable, to_base


@dataclass(frozen=True)
class Item:
    """One line of the shopping list."""

    name: str
    amount: float
    unit: str

    def __str__(self) -> str:
        if self.unit == "piece":
            return f"{self.amount:g} {self.name}"
        return f"{self.amount:g} {self.unit} {self.name}"


def shopping_list(plan: dict[str, int]) -> list[Item]:
    """Everything to buy for a meal plan that maps recipe names to servings.

    The recipes are the ones loaded from the recipe folder. An ingredient used by several
    recipes is listed once: names match ignoring case and surrounding spaces, and amounts
    are added up in base units. An ingredient measured both by weight and by volume gets
    one line for each. Items are sorted by name.
    """
    missing = sorted(set(plan) - set(LOADED))
    if missing:
        raise KeyError(f"unknown recipes: {', '.join(missing)}")
    totals: dict[tuple[str, str], float] = {}
    for name, servings in plan.items():
        for item in scale(LOADED[name], servings).ingredients:
            amount, dimension = to_base(item.amount, item.unit)
            key = (item.name.strip(), dimension)
            totals[key] = totals.get(key, 0.0) + amount
    items = []
    for (name, dimension), amount in sorted(totals.items()):
        shown, unit = readable(amount, dimension)
        items.append(Item(name, shown, unit))
    return items


def as_text(items: list[Item]) -> str:
    """The list as text, one item per line."""
    return "\n".join(str(item) for item in items)

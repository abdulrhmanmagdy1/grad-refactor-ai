"""Recipes and their ingredients."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ingredient:
    """An amount of one ingredient; `unit` is one of the canonical units of recipes.units."""

    name: str
    amount: float
    unit: str = "piece"


@dataclass(frozen=True)
class Recipe:
    """A recipe that feeds `servings` people."""

    name: str
    servings: int
    ingredients: tuple[Ingredient, ...] = ()
    steps: tuple[str, ...] = ()

    def ingredient(self, name: str) -> Ingredient:
        """The ingredient called `name`, ignoring case."""
        for item in self.ingredients:
            if item.name.lower() == name.lower():
                return item
        raise KeyError(f"{self.name} has no {name}")

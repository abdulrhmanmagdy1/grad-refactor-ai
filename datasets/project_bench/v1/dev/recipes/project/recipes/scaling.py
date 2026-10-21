"""Rewriting a recipe for a different number of servings."""

from __future__ import annotations

import math
from dataclasses import replace

from recipes.models import Ingredient, Recipe


def scaled_amount(amount: float, servings: int, wanted: int) -> float:
    """An amount meant for `servings` people, scaled to feed `wanted` people."""
    return amount * wanted / servings


def round_pieces(amount: float) -> int:
    """Whole pieces to buy, rounded up: 2.1 eggs means 3 eggs."""
    return math.ceil(amount - 1e-9)


def scale(recipe: Recipe, wanted: int) -> Recipe:
    """A copy of the recipe for `wanted` servings.

    Every amount grows or shrinks in proportion; ingredients counted in pieces are
    rounded up to whole pieces.
    """
    if wanted < 1:
        raise ValueError("a recipe is for at least one serving")
    ingredients: list[Ingredient] = []
    for item in recipe.ingredients:
        amount = scaled_amount(item.amount, wanted, recipe.servings)
        if item.unit == "piece":
            amount = round_pieces(amount)
        ingredients.append(replace(item, amount=amount))
    return replace(recipe, servings=wanted, ingredients=tuple(ingredients))

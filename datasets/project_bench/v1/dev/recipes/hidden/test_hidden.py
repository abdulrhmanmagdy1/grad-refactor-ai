import logging
from pathlib import Path

import pytest

from recipes.loader import load_folder, parse_ingredient, parse_quantity, parse_recipe
from recipes.models import Ingredient
from recipes.scaling import round_pieces, scale
from recipes.shopping import as_text, shopping_list
from recipes.units import convert, normalize_unit, readable, to_base

PANCAKES = """\
# Pancakes
serves 4

ingredients:
200 g | flour
1 1/2 cups | milk
2 | eggs

steps:
Whisk everything together.
"""

BREAD = """\
# Bread
serves 1

ingredients:
300 g | Flour
1 tsp | salt
"""


def write(folder: Path, name: str, text: str) -> None:
    (folder / f"{name}.recipe").write_text(text, encoding="utf-8")


def amounts(recipe) -> dict[str, float]:
    return {item.name: item.amount for item in recipe.ingredients}


def test_B1_scaling_follows_the_number_of_servings():
    recipe = parse_recipe(PANCAKES)
    doubled = scale(recipe, 8)
    assert doubled.servings == 8
    assert amounts(doubled) == pytest.approx({"flour": 400.0, "milk": 3.0, "eggs": 4})
    halved = scale(recipe, 2)
    assert amounts(halved) == pytest.approx({"flour": 100.0, "milk": 0.75, "eggs": 1})
    assert amounts(scale(recipe, 6))["eggs"] == 3


def test_B2_the_same_ingredient_is_merged_ignoring_case(tmp_path):
    write(tmp_path, "pancakes", PANCAKES)
    write(tmp_path, "bread", BREAD)
    load_folder(tmp_path)
    items = shopping_list({"Pancakes": 4, "Bread": 1})
    flour = [item for item in items if item.name.strip().lower() == "flour"]
    assert len(flour) == 1
    assert (flour[0].amount, flour[0].unit) == (500.0, "g")
    assert len(items) == 4


def test_B3_mass_volume_and_pieces_do_not_convert():
    with pytest.raises(ValueError):
        convert(100, "g", "ml")
    with pytest.raises(ValueError):
        convert(2, "cup", "kg")
    with pytest.raises(ValueError):
        convert(3, "piece", "g")


def test_S1_quantities_are_not_run_as_python():
    with pytest.raises(ValueError):
        parse_quantity("len('abcd')")
    with pytest.raises(ValueError):
        parse_quantity("1 __import__('os').getpid()")


def test_keep_quantities_and_fractions():
    assert parse_quantity("2") == 2.0
    assert parse_quantity("0.5") == 0.5
    assert parse_quantity("1/4") == 0.25
    assert parse_quantity("2 3/4") == 2.75
    assert parse_ingredient("1 1/2 cups | milk") == Ingredient("milk", 1.5, "cup")
    with pytest.raises(ValueError):
        parse_quantity("")


def test_keep_conversions_within_a_dimension():
    assert convert(1.5, "kg", "g") == 1500.0
    assert convert(2, "cup", "ml") == 480.0
    assert convert(500, "ml", "l") == 0.5
    assert convert(4, "piece", "pieces") == 4.0
    assert to_base(2, "tbsp") == (30.0, "volume")
    assert readable(2400.0, "volume") == (2.4, "l")
    assert readable(999.0, "mass") == (999.0, "g")


def test_keep_unit_spellings():
    spellings = {
        "Kilograms": "kg",
        "gr": "g",
        "pcs": "piece",
        "Litres": "l",
        "milliliters": "ml",
        "Teaspoons": "tsp",
        "tablespoon": "tbsp",
        "Cups": "cup",
    }
    assert {text: normalize_unit(text) for text in spellings} == spellings
    with pytest.raises(ValueError):
        normalize_unit("handful")


def test_keep_pieces_round_up_but_not_past_a_whole_number():
    assert round_pieces(2.1) == 3
    assert round_pieces(2.0) == 2
    assert round_pieces(0.1 * 3 / 0.1) == 3
    assert round_pieces(1.1 * 1.1 * 100) == 121


def test_keep_a_bad_file_is_logged_and_stops_the_load(tmp_path, caplog):
    write(tmp_path, "pancakes", PANCAKES)
    load_folder(tmp_path)
    write(tmp_path, "zbroken", "# Broken\nserves many\n")
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        load_folder(tmp_path)
    assert "zbroken.recipe" in caplog.text


def test_keep_weight_and_volume_stay_on_separate_lines(tmp_path):
    write(tmp_path, "pancakes", PANCAKES)
    write(tmp_path, "shake", "# Shake\nserves 1\n\ningredients:\n1 cup | flour\n2 l | milk\n")
    load_folder(tmp_path)
    lines = as_text(shopping_list({"Pancakes": 4, "Shake": 1})).splitlines()
    assert lines == ["2 eggs", "200 g flour", "240 ml flour", "2.36 l milk"]

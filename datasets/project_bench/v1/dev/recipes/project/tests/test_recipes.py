from pathlib import Path

import pytest

from recipes.loader import load_folder, parse_quantity, parse_recipe
from recipes.models import Ingredient
from recipes.scaling import scale
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
Fry ladlefuls in a hot pan.
"""

CREPES = """\
# Crepes
serves 2

ingredients:
125 g | flour
250 ml | milk
1 | eggs
1 pinch | salt
"""


def write(folder: Path, name: str, text: str) -> None:
    (folder / f"{name}.recipe").write_text(text, encoding="utf-8")


def test_parse_a_recipe():
    recipe = parse_recipe(PANCAKES)
    assert recipe.name == "Pancakes"
    assert recipe.servings == 4
    assert recipe.ingredients == (
        Ingredient("flour", 200.0, "g"),
        Ingredient("milk", 1.5, "cup"),
        Ingredient("eggs", 2.0, "piece"),
    )
    assert recipe.steps == ("Whisk everything together.", "Fry ladlefuls in a hot pan.")


def test_quantities():
    assert parse_quantity("3") == 3.0
    assert parse_quantity("0.25") == 0.25
    assert parse_quantity("1 1/2") == 1.5


def test_unit_spellings():
    assert normalize_unit("Grams") == "g"
    assert normalize_unit("tbsp.") == "tbsp"
    assert normalize_unit("") == "piece"
    with pytest.raises(ValueError):
        normalize_unit("pinch")


def test_conversions():
    assert to_base(1.5, "cup") == (360.0, "volume")
    assert convert(1.5, "kg", "g") == 1500.0
    assert convert(3, "tsp", "tbsp") == 1.0
    assert readable(1250.0, "mass") == (1.25, "kg")
    assert readable(250.0, "volume") == (250.0, "ml")


def test_scaling_needs_a_serving():
    with pytest.raises(ValueError):
        scale(parse_recipe(PANCAKES), 0)


def test_unknown_unit_in_a_file_stops_the_load(tmp_path):
    write(tmp_path, "crepes", CREPES)
    with pytest.raises(ValueError):
        load_folder(tmp_path)


def test_shopping_list_adds_up_the_same_ingredient(tmp_path):
    write(tmp_path, "pancakes", PANCAKES)
    write(tmp_path, "crepes", CREPES.replace("1 pinch | salt\n", ""))
    assert sorted(load_folder(tmp_path)) == ["Crepes", "Pancakes"]
    items = shopping_list({"Pancakes": 4, "Crepes": 2})
    assert as_text(items).splitlines() == ["3 eggs", "325 g flour", "610 ml milk"]

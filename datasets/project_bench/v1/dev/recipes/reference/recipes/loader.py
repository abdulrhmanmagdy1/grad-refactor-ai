"""Reading recipes from a folder of .recipe text files (the format is in the README)."""

from __future__ import annotations

import logging
from pathlib import Path

from recipes.models import Ingredient, Recipe
from recipes.units import normalize_unit

log = logging.getLogger(__name__)

SECTIONS = ("ingredients", "steps")

# The recipes of the folder loaded last, by name.
LOADED: dict[str, Recipe] = {}


def parse_quantity(text: str) -> float:
    """A quantity written as a whole number, a decimal or a fraction: "2", "0.5", "1 1/2"."""
    parts = text.split()
    if not parts:
        raise ValueError("empty quantity")
    total = 0.0
    for part in parts:
        top, slash, bottom = part.partition("/")
        try:
            total += float(top) / float(bottom) if slash else float(part)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"not a quantity: {text!r}") from exc
    return total


def parse_ingredient(line: str) -> Ingredient:
    """One ingredient line, "<quantity> [unit] | <name>", such as "1 1/2 cups | milk"."""
    measure, bar, name = line.partition("|")
    if not bar or not name.strip():
        raise ValueError(f"expected '<quantity> [unit] | <name>', got {line!r}")
    words = measure.split()
    unit = "piece"
    if words and words[-1].isalpha():
        unit = normalize_unit(words.pop())
    return Ingredient(name.strip(), parse_quantity(" ".join(words)), unit)


def parse_servings(line: str) -> int:
    """The number of a "serves 4" line."""
    word, _, number = line.partition(" ")
    number = number.strip()
    if word.lower() != "serves" or not number.isdigit() or int(number) < 1:
        raise ValueError(f"expected 'serves <n>', got {line!r}")
    return int(number)


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    """The lines under each "ingredients:" and "steps:" heading."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        heading = line.lower().rstrip(":")
        if line.endswith(":") and heading in SECTIONS:
            current = sections.setdefault(heading, [])
        elif current is None:
            raise ValueError(f"line outside a section: {line!r}")
        else:
            current.append(line)
    return sections


def parse_recipe(text: str) -> Recipe:
    """Parse the text of one .recipe file."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or not lines[0].startswith("# "):
        raise ValueError("a recipe starts with '# <name>' and 'serves <n>'")
    sections = split_sections(lines[2:])
    ingredients = tuple(parse_ingredient(line) for line in sections.get("ingredients", []))
    steps = tuple(sections.get("steps", []))
    return Recipe(lines[0][2:].strip(), parse_servings(lines[1]), ingredients, steps)


def load_folder(folder: Path) -> dict[str, Recipe]:
    """Read every .recipe file in `folder`; afterwards LOADED holds exactly these recipes.

    A file that cannot be read stops the load with its error, and LOADED is left as it was.
    """
    found: dict[str, Recipe] = {}
    for path in sorted(Path(folder).glob("*.recipe")):
        try:
            recipe = parse_recipe(path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("cannot read recipe file %s", path.name)
            raise
        found[recipe.name] = recipe
    LOADED.clear()
    LOADED.update(found)
    return found

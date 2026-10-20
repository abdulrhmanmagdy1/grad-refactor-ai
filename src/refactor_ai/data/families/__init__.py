"""Team-authored template families, registered by stable key (the source group)."""

from refactor_ai.data.families import (  # noqa: F401 - importing registers the families
    access,
    commerce,
    finance,
    logistics,
    people,
    systems,
    text,
)
from refactor_ai.data.families.base import FAMILIES, Family, Param, Variant


def all_families() -> list[Family]:
    return [FAMILIES[key] for key in sorted(FAMILIES)]


__all__ = ["FAMILIES", "Family", "Param", "Variant", "all_families"]

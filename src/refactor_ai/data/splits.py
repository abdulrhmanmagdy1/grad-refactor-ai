"""Split assignment by source group.

Template families are the unit of assignment: every variant of a family lands in the
same split, so the held-out splits contain only families that training never sees.
Held-out families are drawn with a seeded shuffle, at most one family per category
while categories remain, so validation and test each cover several domains. Each
licensed-source item is its own source group and goes to the test split (see
docs/data-and-training/data-plan.md for the rationale).
"""

from __future__ import annotations

import random

SPLITS = ("train", "validation", "test")


def assign_family_splits(
    families: list[tuple[str, str]],
    *,
    seed: int,
    validation: int,
    test: int,
    train_only: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Map family key to split. families holds (key, category) pairs.

    Families in train_only are never drawn for a held-out split (for example because
    their domain resembles fixtures another workstream trains on).
    """
    eligible = [item for item in families if item[0] not in train_only]
    if validation + test > len(eligible) or validation + test >= len(families):
        raise ValueError("not enough families for the requested held-out splits")
    order = sorted(eligible)
    random.Random(f"{seed}:family-splits").shuffle(order)
    chosen: dict[str, list[str]] = {"test": [], "validation": []}
    for split, wanted in (("test", test), ("validation", validation)):
        categories: set[str] = set()
        taken = set(chosen["test"]) | set(chosen["validation"])
        for key, category in order:
            if len(chosen[split]) >= wanted:
                break
            if key not in taken and category not in categories:
                chosen[split].append(key)
                categories.add(category)
                taken.add(key)
        for key, _category in order:
            if len(chosen[split]) >= wanted:
                break
            if key not in taken:
                chosen[split].append(key)
                taken.add(key)
    assignment = {key: "train" for key, _ in families}
    for split in ("validation", "test"):
        for key in chosen[split]:
            assignment[key] = split
    return assignment

"""Shared helpers for writing family builders concisely."""

from __future__ import annotations

import random

from refactor_ai.data.families.base import Check, Param, Variant, choose_styles, maybe, pick

BLOCK_STARTS = ("if ", "for ", "while ")
SUBSET_PROBABILITY = 0.2


def core_has_block(core: list[str]) -> bool:
    return any(line.startswith(BLOCK_STARTS) for line in core)


def subset_checks(rng: random.Random, checks: list[Check], core: list[str]):
    """Keep a non-empty proper subset of the checks in their original order.

    Setup statements of a dropped check move to the next kept check (or to the start of
    the core), so names they define stay available. This yields functions with fewer
    guards, down to a single one.
    """
    count = rng.randrange(1, len(checks))
    keep = set(rng.sample(range(len(checks)), count))
    kept: list[Check] = []
    carry: list[str] = []
    for index, check in enumerate(checks):
        if index in keep:
            kept.append(Check(check.ok, check.bad, check.fail, tuple(carry) + check.setup))
            carry = []
        else:
            carry += list(check.setup)
    return kept, carry + list(core)


def make(
    rng: random.Random,
    name: str,
    params: list[Param],
    checks: list[Check],
    core: list[str],
    *,
    docs: tuple[str, ...] = (),
    returns: str | None = None,
    prelude: list[str] | tuple[str, ...] = (),
    tail: list[str] | tuple[str, ...] = (),
    doc_probability: float = 0.5,
    annotate_probability: float = 0.35,
    styles: list[str] | None = None,
) -> Variant:
    """Assemble a variant: optionally fewer checks, then layout, docstring, annotations."""
    if styles is None and len(checks) >= 2 and maybe(rng, SUBSET_PROBABILITY):
        checks, core = subset_checks(rng, checks, core)
    if styles is None:
        styles = choose_styles(rng, len(checks), allow_elif=core_has_block(core))
    doc = pick(rng, docs) if docs and maybe(rng, doc_probability) else None
    return Variant(
        name=name,
        params=params,
        checks=checks,
        core=list(core),
        styles=styles,
        doc=doc,
        annotate=maybe(rng, annotate_probability),
        returns_annotation=returns,
        prelude=list(prelude),
        tail=list(tail),
    )


def shuffled(rng: random.Random, items: list) -> list:
    items = list(items)
    rng.shuffle(items)
    return items


def around(*values: int | float) -> tuple:
    """Boundary pool: each value with its neighbours one unit away, sorted and unique."""
    pool: set = set()
    for value in values:
        pool.update({value - 1, value, value + 1})
    return tuple(sorted(pool))

"""Per-group summaries of one numeric column."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

SORTABLE_FIELDS = frozenset({"count", "total", "mean", "minimum", "maximum"})


@dataclass(frozen=True)
class GroupSummary:
    """Figures for one group; ``total`` is rounded to cents, ``mean`` is total / count."""

    key: str
    count: int
    total: float
    mean: float
    minimum: float
    maximum: float


def summarize(
    rows: Iterable[Mapping[str, object]], group_by: str, value_column: str
) -> list[GroupSummary]:
    """Group cleaned rows by ``group_by`` and summarize ``value_column``.

    The result has one summary per group, sorted by group key.
    """
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        buckets[str(row[group_by])].append(float(row[value_column]))
    return [_summarize_group(key, values) for key, values in sorted(buckets.items())]


def _summarize_group(key: str, values: list[float]) -> GroupSummary:
    total = round(math.fsum(values), 2)
    return GroupSummary(
        key=key,
        count=len(values),
        total=total,
        mean=total / len(values),
        minimum=min(values),
        maximum=max(values),
    )


def top_groups(
    summaries: Iterable[GroupSummary], n: int, by: str = "total"
) -> list[GroupSummary]:
    """The ``n`` groups with the largest ``by`` figure, ties broken by key."""
    if by not in SORTABLE_FIELDS:
        raise ValueError(f"cannot rank groups by {by!r}")
    ranked = sorted(summaries, key=lambda summary: (-getattr(summary, by), summary.key))
    return ranked[: max(n, 0)]


def shares(summaries: Iterable[GroupSummary]) -> dict[str, float]:
    """Each group's share of the grand total in percent; all 0 when it is 0."""
    items = list(summaries)
    grand_total = math.fsum(summary.total for summary in items)
    if grand_total == 0:
        return {summary.key: 0.0 for summary in items}
    return {summary.key: 100.0 * summary.total / grand_total for summary in items}

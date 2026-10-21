"""Word and n-gram frequencies."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def count_words(tokens: Iterable[str]) -> dict[str, int]:
    """Return how many times each token occurs."""
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def ngrams(tokens: Sequence[str], n: int) -> list[tuple[str, ...]]:
    """Return every run of ``n`` consecutive tokens, in order of appearance.

    The runs overlap: one starts at every position that still has ``n`` tokens from
    there to the end. There are none when ``tokens`` has fewer than ``n`` items.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    return [tuple(tokens[start : start + n]) for start in range(len(tokens) - n + 1)]


def count_ngrams(tokens: Sequence[str], n: int) -> dict[str, int]:
    """Count the n-grams of ``tokens``; each key is the n-gram joined by spaces."""
    return count_words(" ".join(gram) for gram in ngrams(tokens, n))


def top_n(counts: dict[str, int], n: int) -> list[tuple[str, int]]:
    """Return the ``n`` most frequent entries as (item, count) pairs.

    The highest counts come first; entries with the same count are listed in
    alphabetical order.
    """
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return ranked[:n]


def drop_rare(counts: dict[str, int], min_count: int) -> dict[str, int]:
    """Delete, in place, the entries counted fewer than ``min_count`` times.

    Returns ``counts`` so calls can be chained.
    """
    for item in list(counts):
        if counts[item] < min_count:
            del counts[item]
    return counts

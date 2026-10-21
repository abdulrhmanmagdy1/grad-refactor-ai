"""Turning assessment scores into course percentages and letter grades."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gradebook.models import Assessment

LETTER_BANDS: tuple[tuple[float, str], ...] = (
    (90.0, "A"),
    (80.0, "B"),
    (70.0, "C"),
    (60.0, "D"),
)


def weighted_percentage(assessments: Sequence[Assessment], scores: Mapping[str, float]) -> float:
    """Course percentage from 0-100 scores, rounded to one decimal.

    Each score counts in proportion to its assessment's weight, and an
    assessment without a score counts as zero.
    """
    total_weight = sum(assessment.weight for assessment in assessments)
    if total_weight <= 0:
        raise ValueError("the course has no weighted assessments")
    earned = sum(scores.get(item.name, 0.0) * item.weight for item in assessments)
    return round(earned / total_weight, 1)


def letter_grade(percentage: float) -> str:
    """Letter for a course percentage.

    90 and above is an A, 80 up to 90 a B, 70 up to 80 a C, 60 up to 70 a D,
    and anything below 60 an F.
    """
    for lowest, letter in LETTER_BANDS:
        if percentage >= lowest:
            return letter
    return "F"


def quiz_average(scores: Sequence[float]) -> float:
    """Average quiz score once the single lowest quiz is dropped.

    With only one quiz nothing is dropped; with none the average is 0.0.
    """
    if len(scores) <= 1:
        return float(sum(scores))
    kept = sorted(scores)[1:]
    return sum(kept) / len(kept)


def class_summary(percentages: Sequence[float]) -> dict[str, float]:
    """Mean, highest and lowest percentage of a class, the mean rounded to one decimal."""
    if not percentages:
        raise ValueError("the class has no percentages yet")
    return {
        "mean": round(sum(percentages) / len(percentages), 1),
        "high": max(percentages),
        "low": min(percentages),
    }


def letter_distribution(percentages: Sequence[float]) -> dict[str, int]:
    """How many students got each letter, A to F, including letters nobody got."""
    counts = {letter: 0 for _, letter in LETTER_BANDS}
    counts["F"] = 0
    for percentage in percentages:
        counts[letter_grade(percentage)] += 1
    return counts

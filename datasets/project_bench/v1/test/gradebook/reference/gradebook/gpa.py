"""Grade point averages and academic standing."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from gradebook import transcript
from gradebook.models import CourseResult

GRADE_POINTS: dict[str, float] = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}


def grade_point_average(results: Iterable[CourseResult]) -> float:
    """Credit-weighted mean of grade points, rounded to two decimals.

    Withdrawals (W) and pass/fail passes (P) carry no grade points and are
    left out of the average entirely. With no graded course the GPA is 0.0.
    """
    points = 0.0
    credits = 0
    for result in results:
        if result.letter not in GRADE_POINTS:
            continue
        points += GRADE_POINTS[result.letter] * result.credits
        credits += result.credits
    if credits == 0:
        return 0.0
    return round(points / credits, 2)


def term_averages(results: Iterable[CourseResult]) -> dict[str, float]:
    """GPA of every term, in chronological order."""
    return {
        term: grade_point_average(term_results)
        for term, term_results in transcript.by_term(results).items()
    }


def academic_standing(cumulative: float) -> str:
    """Standing for a cumulative GPA: dean's list, probation or good standing."""
    if cumulative >= 3.5:
        return "dean's list"
    if cumulative < 2.0:
        return "probation"
    return "good standing"


def deans_list(averages: Mapping[str, float]) -> list[str]:
    """Ids of the students whose GPA puts them on the dean's list, sorted."""
    return sorted(student_id for student_id, value in averages.items() if value >= 3.5)


def probation_list(averages: Mapping[str, float]) -> list[str]:
    """Ids of the students on academic probation, sorted."""
    return sorted(student_id for student_id, value in averages.items() if value < 2.0)

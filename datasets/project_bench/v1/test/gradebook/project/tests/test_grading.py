import pytest

from gradebook.grading import (
    class_summary,
    letter_distribution,
    letter_grade,
    quiz_average,
    weighted_percentage,
)
from gradebook.models import Assessment

ASSESSMENTS = [Assessment("Midterm", 0.3), Assessment("Final", 0.5), Assessment("Quizzes", 0.2)]


def test_weighted_percentage() -> None:
    scores = {"Midterm": 80, "Final": 90, "Quizzes": 70}
    assert weighted_percentage(ASSESSMENTS, scores) == 83.0


def test_missing_score_counts_as_zero() -> None:
    assert weighted_percentage(ASSESSMENTS, {"Final": 90}) == 45.0


def test_weighted_percentage_needs_weights() -> None:
    with pytest.raises(ValueError):
        weighted_percentage([], {})


def test_letter_grades() -> None:
    assert letter_grade(97.5) == "A"
    assert letter_grade(85.5) == "B"
    assert letter_grade(72.0) == "C"
    assert letter_grade(64.3) == "D"
    assert letter_grade(41.0) == "F"


def test_quiz_average() -> None:
    assert quiz_average([50, 80, 90]) == 85.0
    assert quiz_average([70]) == 70.0
    assert quiz_average([]) == 0.0


def test_class_summary() -> None:
    assert class_summary([72.5, 88.0, 64.0]) == {"mean": 74.8, "high": 88.0, "low": 64.0}
    with pytest.raises(ValueError):
        class_summary([])


def test_letter_distribution_lists_every_letter() -> None:
    assert letter_distribution([95.0, 85.0, 86.5, 30.0]) == {
        "A": 1,
        "B": 2,
        "C": 0,
        "D": 0,
        "F": 1,
    }

from gradebook.gpa import (
    academic_standing,
    deans_list,
    grade_point_average,
    probation_list,
    term_averages,
)
from gradebook.models import CourseResult, Student
from gradebook.transcript import by_term, credits_earned, render_transcript

RESULTS = [
    CourseResult("2025-2", "MATH201", "Linear Algebra", 4, "B"),
    CourseResult("2025-1", "MATH101", "Algebra I", 4, "A"),
    CourseResult("2025-1", "HIST110", "Modern History", 3, "C"),
    CourseResult("2025-2", "PHYS101", "Mechanics", 4, "F"),
]


def test_gpa_is_credit_weighted() -> None:
    assert grade_point_average(RESULTS[1:3]) == 3.14
    assert grade_point_average(RESULTS) == 2.27
    assert grade_point_average([]) == 0.0


def test_term_averages_in_term_order() -> None:
    assert term_averages(RESULTS) == {"2025-1": 3.14, "2025-2": 1.5}
    assert list(term_averages(RESULTS)) == ["2025-1", "2025-2"]


def test_academic_standing() -> None:
    assert academic_standing(3.8) == "dean's list"
    assert academic_standing(2.9) == "good standing"
    assert academic_standing(1.4) == "probation"


def test_deans_and_probation_lists() -> None:
    averages = {"s-003": 3.9, "s-001": 3.7, "s-002": 2.4, "s-004": 1.2}
    assert deans_list(averages) == ["s-001", "s-003"]
    assert probation_list(averages) == ["s-004"]


def test_by_term_groups_and_sorts() -> None:
    grouped = by_term(RESULTS)
    assert list(grouped) == ["2025-1", "2025-2"]
    assert [result.course_code for result in grouped["2025-1"]] == ["HIST110", "MATH101"]


def test_failed_courses_earn_no_credits() -> None:
    assert credits_earned(RESULTS) == 11


def test_transcript_text() -> None:
    student = Student("s-001", "Lina Haddad", "BSc Mathematics")
    text = render_transcript(student, RESULTS, issued_on="2026-01-15")
    assert "Student:    Lina Haddad" in text
    assert text.index("Term 2025-1") < text.index("Term 2025-2")
    assert "Credits earned 7 of 7, term GPA 3.14" in text
    assert "Credits earned 4 of 8, term GPA 1.50" in text
    assert "Credits attempted: 15" in text
    assert "Cumulative GPA:    2.27" in text
    assert "Standing:          good standing" in text
    assert "Withdrawals" not in text


def test_empty_transcript() -> None:
    student = Student("s-009", "Omar Said", "BA History")
    text = render_transcript(student, [], issued_on="2026-01-15")
    assert "No results on record." in text

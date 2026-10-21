import pytest

from gradebook.gpa import (
    academic_standing,
    deans_list,
    grade_point_average,
    probation_list,
    term_averages,
)
from gradebook.grading import letter_grade, quiz_average
from gradebook.importer import ScoreImporter
from gradebook.models import Assessment, Course, CourseResult, Student
from gradebook.service import GradeBook
from gradebook.transcript import render_transcript


def _book() -> GradeBook:
    book = GradeBook("2025-1")
    book.add_course(
        Course("MATH101", "Algebra I", 4, "t.hall", [Assessment("Midterm", 40), Assessment("Final", 60)])
    )
    book.add_course(Course("HIST110", "Modern History", 3, "j.ng", [Assessment("Essay", 1)]))
    for course_code in ("MATH101", "HIST110"):
        book.enroll(course_code, "s-001")
        book.enroll(course_code, "s-002")
    return book


# --- seeded issues -------------------------------------------------------


def test_B1_courses_do_not_share_their_assessments() -> None:
    drawing = Course("ART101", "Drawing", 3, "m.cole")
    painting = Course("ART102", "Painting", 3, "m.cole")
    drawing.add_assessment(Assessment("Portfolio", 1.0))
    assert painting.assessments == []
    assert [assessment.name for assessment in drawing.assessments] == ["Portfolio"]


def test_B2_band_boundaries_get_the_higher_letter() -> None:
    assert letter_grade(90.0) == "A"
    assert letter_grade(80.0) == "B"
    assert letter_grade(70.0) == "C"
    assert letter_grade(60.0) == "D"
    assert letter_grade(59.9) == "F"


def test_B3_withdrawals_and_passes_are_left_out_of_the_gpa() -> None:
    results = [
        CourseResult("2025-1", "MATH101", "Algebra I", 3, "A"),
        CourseResult("2025-1", "HIST110", "Modern History", 4, "W"),
        CourseResult("2025-1", "ART100", "Studio Basics", 2, "P"),
    ]
    assert grade_point_average(results) == 4.0
    mixed = [
        CourseResult("2025-2", "MATH201", "Linear Algebra", 3, "B"),
        CourseResult("2025-2", "PHYS101", "Mechanics", 3, "C"),
        CourseResult("2025-2", "CHEM101", "Chemistry", 3, "W"),
    ]
    assert grade_point_average(mixed) == 2.5


def test_S1_only_the_instructor_can_record_scores() -> None:
    book = _book()
    with pytest.raises(PermissionError):
        book.record_score("j.ng", "MATH101", "s-001", "Final", 100)
    assert book.scores("MATH101", "s-001") == {}
    assert book.audit_log == []


# --- behaviour that must not change ---------------------------------------


def test_keep_instructors_record_and_publish_their_own_courses() -> None:
    book = _book()
    book.record_score("t.hall", "MATH101", "s-001", "Midterm", 85)
    book.record_score("t.hall", "MATH101", "s-001", "Final", 95)
    book.record_score("j.ng", "HIST110", "s-002", "Essay", 67)
    assert book.percentage("MATH101", "s-001") == 91.0
    assert book.audit_log == [
        ("t.hall", "MATH101", "s-001", "Midterm", 85.0),
        ("t.hall", "MATH101", "s-001", "Final", 95.0),
        ("j.ng", "HIST110", "s-002", "Essay", 67.0),
    ]
    published = book.publish("j.ng", "HIST110")
    assert {student: result.letter for student, result in published.items()} == {
        "s-001": "F",
        "s-002": "D",
    }


def test_keep_record_quizzes_for_the_instructor() -> None:
    book = GradeBook("2025-1")
    book.add_course(Course("CHEM101", "Chemistry", 3, "r.diaz", [Assessment("Quizzes", 1)]))
    book.enroll("CHEM101", "s-001")
    book.record_quizzes("r.diaz", "CHEM101", "s-001", [55, 65, 95])
    assert book.scores("CHEM101", "s-001") == {"Quizzes": 80.0}
    with pytest.raises(PermissionError):
        book.record_quizzes("t.hall", "CHEM101", "s-001", [100, 100])


def test_keep_quiz_average_drops_only_the_lowest_quiz() -> None:
    assert quiz_average([50, 80, 90]) == 85.0
    assert quiz_average([60, 60, 90]) == 75.0
    assert quiz_average([90, 40]) == 90.0
    assert quiz_average([70]) == 70.0
    assert quiz_average([]) == 0.0


def test_keep_an_identical_sheet_is_imported_once() -> None:
    book = _book()
    importer = ScoreImporter(book, "t.hall")
    sheet = "student_id,assessment,score\ns-001,Midterm,77\ns-002,Final,64.5\n"
    assert importer.import_text("MATH101", sheet) == 2
    assert importer.import_text("MATH101", sheet) == 0
    changed = "student_id,assessment,score\ns-001,Midterm,79\n"
    assert importer.import_text("MATH101", changed) == 1
    assert book.scores("MATH101", "s-001") == {"Midterm": 79.0}
    assert len(book.audit_log) == 3


def test_keep_letters_inside_the_bands() -> None:
    assert letter_grade(100.0) == "A"
    assert letter_grade(90.1) == "A"
    assert letter_grade(89.9) == "B"
    assert letter_grade(79.9) == "C"
    assert letter_grade(60.1) == "D"
    assert letter_grade(0.0) == "F"


def test_keep_gpa_of_graded_courses() -> None:
    results = [
        CourseResult("2025-1", "MATH101", "Algebra I", 4, "A"),
        CourseResult("2025-1", "HIST110", "Modern History", 3, "C"),
        CourseResult("2025-2", "PHYS101", "Mechanics", 4, "F"),
    ]
    assert grade_point_average(results) == 2.0
    assert term_averages(results) == {"2025-1": 3.14, "2025-2": 0.0}
    assert grade_point_average([]) == 0.0


def test_keep_standing_thresholds() -> None:
    assert academic_standing(3.5) == "dean's list"
    assert academic_standing(3.49) == "good standing"
    assert academic_standing(2.0) == "good standing"
    assert academic_standing(1.99) == "probation"
    averages = {"s-001": 3.5, "s-002": 3.49, "s-003": 2.0, "s-004": 1.99}
    assert deans_list(averages) == ["s-001"]
    assert probation_list(averages) == ["s-004"]


def test_keep_transcript_summary() -> None:
    student = Student("s-001", "Lina Haddad", "BSc Mathematics")
    results = [
        CourseResult("2025-2", "MATH201", "Linear Algebra and Its Applications to Data", 4, "B"),
        CourseResult("2025-1", "MATH101", "Algebra I", 4, "A"),
        CourseResult("2025-1", "HIST110", "Modern History", 3, "C"),
    ]
    text = render_transcript(student, results, issued_on="2026-01-15")
    assert "Linear Algebra and Its Applicatio~" in text
    assert "Credits earned 7 of 7, term GPA 3.14" in text
    assert "Credits earned:    11" in text
    assert "Cumulative GPA:    3.09" in text
    assert text.splitlines()[-1].strip() == "End of transcript"


def test_keep_assessments_given_to_a_course_are_used() -> None:
    course = Course("BIO101", "Biology", 3, "r.diaz", [Assessment("Lab", 30)])
    course.add_assessment(Assessment("Exam", 70))
    assert [assessment.name for assessment in course.assessments] == ["Lab", "Exam"]
    with pytest.raises(ValueError):
        course.add_assessment(Assessment("Lab", 10))
    with pytest.raises(ValueError):
        course.add_assessment(Assessment("Bonus", 0))

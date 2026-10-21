import pytest

from gradebook.importer import ScoreImporter, parse_sheet
from gradebook.models import Assessment, Course
from gradebook.service import GradeBook


def make_book() -> GradeBook:
    course = Course(
        "MATH101",
        "Algebra I",
        4,
        "t.hall",
        [Assessment("Midterm", 40), Assessment("Final", 60)],
    )
    book = GradeBook("2025-1")
    book.add_course(course)
    book.enroll("MATH101", "s-001")
    book.enroll("MATH101", "s-002")
    return book


def test_record_and_percentage() -> None:
    book = make_book()
    book.record_score("t.hall", "MATH101", "s-001", "Midterm", 85)
    book.record_score("t.hall", "MATH101", "s-001", "Final", 95)
    assert book.scores("MATH101", "s-001") == {"Midterm": 85.0, "Final": 95.0}
    assert book.percentage("MATH101", "s-001") == 91.0
    assert book.audit_log[-1] == ("t.hall", "MATH101", "s-001", "Final", 95.0)


def test_record_rejects_bad_input() -> None:
    book = make_book()
    with pytest.raises(KeyError):
        book.record_score("t.hall", "MATH101", "s-777", "Final", 80)
    with pytest.raises(KeyError):
        book.record_score("t.hall", "MATH101", "s-001", "Essay", 80)
    with pytest.raises(ValueError):
        book.record_score("t.hall", "MATH101", "s-001", "Final", 101)


def test_publish_fixes_letters() -> None:
    book = make_book()
    for assessment, score in (("Midterm", 85), ("Final", 95)):
        book.record_score("t.hall", "MATH101", "s-001", assessment, score)
    for assessment, score in (("Midterm", 70), ("Final", 75)):
        book.record_score("t.hall", "MATH101", "s-002", assessment, score)
    published = book.publish("t.hall", "MATH101")
    assert {student: result.letter for student, result in published.items()} == {
        "s-001": "A",
        "s-002": "C",
    }
    assert [result.course_code for result in book.results_for("s-002")] == ["MATH101"]
    with pytest.raises(ValueError):
        book.record_score("t.hall", "MATH101", "s-001", "Final", 100)


def test_only_the_instructor_publishes() -> None:
    book = make_book()
    with pytest.raises(PermissionError):
        book.publish("j.ng", "MATH101")


def test_record_quizzes_stores_their_average() -> None:
    course = Course("CHEM101", "Chemistry", 3, "r.diaz", [Assessment("Quizzes", 1)])
    book = GradeBook("2025-1")
    book.add_course(course)
    book.enroll("CHEM101", "s-001")
    book.record_quizzes("r.diaz", "CHEM101", "s-001", [40, 70, 85, 90])
    assert book.scores("CHEM101", "s-001") == {"Quizzes": 81.7}


def test_add_assessment_keeps_names_unique() -> None:
    course = Course("BIO101", "Biology", 3, "r.diaz", [Assessment("Lab", 30)])
    course.add_assessment(Assessment("Exam", 70))
    assert course.assessment_names() == {"Lab", "Exam"}
    with pytest.raises(ValueError):
        course.add_assessment(Assessment("Lab", 10))


def test_import_sheet_once(tmp_path) -> None:
    book = make_book()
    importer = ScoreImporter(book, "t.hall")
    sheet = tmp_path / "math101.csv"
    sheet.write_text("student_id,assessment,score\ns-001,Midterm,77\ns-002, Final ,64.5\n")
    assert importer.import_file("MATH101", sheet) == 2
    assert importer.import_file("MATH101", sheet) == 0
    assert book.scores("MATH101", "s-002") == {"Final": 64.5}


def test_parse_sheet_rejects_bad_sheets() -> None:
    with pytest.raises(ValueError, match="score"):
        parse_sheet("student_id,assessment\ns-001,Final\n")
    with pytest.raises(ValueError, match="line 3"):
        parse_sheet("student_id,assessment,score\ns-001,Final,80\ns-002,Final,eighty\n")

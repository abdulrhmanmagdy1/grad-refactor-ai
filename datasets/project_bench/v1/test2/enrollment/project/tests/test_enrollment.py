from datetime import date

import pytest

from enrollment.catalog import Catalog, CatalogError
from enrollment.certificates import CertificateError, CertificateIssuer
from enrollment.models import Question, Quiz, Role, User
from enrollment.progress import ProgressError, ProgressTracker
from enrollment.quizzes import Gradebook, grade, is_passing
from enrollment.registration import EnrollmentError, Placement, Registrar
from enrollment.transcript import build_transcript

TEACHER = User("t1", "Dr. Lane", Role.INSTRUCTOR)
STUDENT = User("s1", "Sam", Role.STUDENT)


def make_platform(tmp_path):
    catalog = Catalog()
    catalog.add_course("PY101", "Python Basics", 2, "t1", prerequisites=[])
    catalog.add_course("PY201", "Python Projects", 1, "t1", prerequisites=["PY101"])
    for lesson in ("intro", "loops", "functions"):
        catalog.add_lesson("PY101", lesson)
    questions = [Question(f"q{i}", ("a", "b", "c"), i % 3) for i in range(10)]
    catalog.add_quiz(Quiz("PY101-final", "PY101", questions))
    registrar = Registrar(catalog)
    tracker = ProgressTracker(catalog, registrar)
    gradebook = Gradebook(catalog)
    issuer = CertificateIssuer(catalog, registrar, tracker, gradebook, tmp_path)
    return catalog, registrar, tracker, gradebook, issuer


def perfect_answers(n=10):
    return {i: i % 3 for i in range(n)}


def test_enroll_until_full_then_waitlist(tmp_path):
    _, registrar, *_ = make_platform(tmp_path)
    assert registrar.enroll("a", "PY101") is Placement.ENROLLED
    assert registrar.enroll("b", "PY101") is Placement.ENROLLED
    assert registrar.enroll("c", "PY101") is Placement.WAITLISTED
    assert registrar.waitlist("PY101") == ["c"]


def test_double_enrollment_is_refused(tmp_path):
    _, registrar, *_ = make_platform(tmp_path)
    registrar.enroll("a", "PY101")
    with pytest.raises(EnrollmentError):
        registrar.enroll("a", "PY101")


def test_drop_promotes_waitlisted_student(tmp_path):
    _, registrar, *_ = make_platform(tmp_path)
    for student in ("a", "b", "c"):
        registrar.enroll(student, "PY101")
    assert registrar.drop("a", "PY101") == "c"
    assert registrar.enrolled("PY101") == ["b", "c"]


def test_missing_prerequisite_blocks_enrollment(tmp_path):
    _, registrar, *_ = make_platform(tmp_path)
    with pytest.raises(EnrollmentError):
        registrar.enroll("a", "PY201")
    registrar.record_completion("a", "PY101")
    assert registrar.enroll("a", "PY201") is Placement.ENROLLED


def test_unknown_prerequisite_is_rejected():
    catalog = Catalog()
    with pytest.raises(CatalogError):
        catalog.add_course("X", "X", 5, "t1", prerequisites=["NOPE"])


def test_progress_percent_rounds_down(tmp_path):
    _, registrar, tracker, *_ = make_platform(tmp_path)
    registrar.enroll("a", "PY101")
    tracker.complete_lesson("a", "PY101", "intro")
    assert tracker.percent_complete("a", "PY101") == 33
    assert tracker.next_lesson("a", "PY101") == "loops"
    with pytest.raises(ProgressError):
        tracker.complete_lesson("a", "PY101", "classes")


def test_grading_counts_points(tmp_path):
    catalog, *_ = make_platform(tmp_path)
    answers = perfect_answers()
    answers[0] = 2
    result = grade(catalog.quiz("PY101-final"), "a", answers)
    assert (result.score, result.max_score) == (9, 10)
    assert is_passing(result)


def test_student_cannot_override_scores(tmp_path):
    _, _, _, gradebook, _ = make_platform(tmp_path)
    with pytest.raises(PermissionError):
        gradebook.override_score(STUDENT, "a", "PY101-final", 10)
    assert gradebook.override_score(TEACHER, "a", "PY101-final", 8).score == 8


def test_certificate_after_completing_course(tmp_path):
    _, registrar, tracker, gradebook, issuer = make_platform(tmp_path)
    registrar.enroll("a", "PY101")
    with pytest.raises(CertificateError):
        issuer.issue("a", "Ann", "PY101", date(2026, 6, 1))
    for lesson in ("intro", "loops", "functions"):
        tracker.complete_lesson("a", "PY101", lesson)
    gradebook.submit("PY101-final", "a", perfect_answers())
    path = issuer.issue("a", "Ann", "PY101", date(2026, 6, 1))
    assert "Ann" in path.read_text(encoding="utf-8")
    assert "PY101" in registrar.completed("a")


def test_transcript_lists_courses(tmp_path):
    catalog, registrar, tracker, gradebook, _ = make_platform(tmp_path)
    registrar.enroll("a", "PY101")
    tracker.complete_lesson("a", "PY101", "intro")
    text = build_transcript("a", catalog, registrar, tracker, gradebook)
    assert "PY101 Python Basics [enrolled]" in text
    assert "lessons: 1/3 (33%)" in text
    assert "quiz PY101-final: not attempted" in text

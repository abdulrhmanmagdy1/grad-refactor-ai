from datetime import date

import pytest

from enrollment.catalog import Catalog
from enrollment.certificates import CertificateIssuer
from enrollment.models import Question, Quiz, Role, User
from enrollment.progress import ProgressTracker
from enrollment.quizzes import Gradebook
from enrollment.registration import EnrollmentError, Placement, Registrar


def make_platform(tmp_path):
    catalog = Catalog()
    catalog.add_course("PY101", "Python Basics", 1, "t1", prerequisites=[])
    catalog.add_course("SQL101", "SQL Basics", 1, "t2", prerequisites=[])
    catalog.add_course("DATA301", "Data Pipelines", 3, "t1", prerequisites=["PY101", "SQL101"])
    for lesson in ("intro", "loops"):
        catalog.add_lesson("PY101", lesson)
    questions = [Question(f"q{i}", ("a", "b"), i % 2) for i in range(10)]
    catalog.add_quiz(Quiz("PY101-final", "PY101", questions))
    registrar = Registrar(catalog)
    tracker = ProgressTracker(catalog, registrar)
    gradebook = Gradebook(catalog)
    issuer = CertificateIssuer(catalog, registrar, tracker, gradebook, tmp_path)
    return catalog, registrar, tracker, gradebook, issuer


def test_B1_default_prerequisites_are_not_shared():
    catalog = Catalog()
    catalog.add_course("BASE", "Base", 5, "t1")
    catalog.add_course("ART", "Art", 5, "t1")
    catalog.add_course("MUSIC", "Music", 5, "t1")
    catalog.add_prerequisite("ART", "BASE")
    assert catalog.course("MUSIC").prerequisites == []
    assert catalog.course("BASE").prerequisites == []
    assert catalog.course("ART").prerequisites == ["BASE"]


def test_B2_longest_waiting_student_is_promoted(tmp_path):
    _, registrar, *_ = make_platform(tmp_path)
    registrar.enroll("a", "PY101")
    assert registrar.enroll("b", "PY101") is Placement.WAITLISTED
    assert registrar.enroll("c", "PY101") is Placement.WAITLISTED
    assert registrar.drop("a", "PY101") == "b"
    assert registrar.enrolled("PY101") == ["b"]
    assert registrar.waitlist("PY101") == ["c"]


def test_B3_every_prerequisite_is_required(tmp_path):
    _, registrar, *_ = make_platform(tmp_path)
    registrar.record_completion("a", "PY101")
    with pytest.raises(EnrollmentError):
        registrar.enroll("a", "DATA301")
    registrar.record_completion("a", "SQL101")
    assert registrar.enroll("a", "DATA301") is Placement.ENROLLED


def test_S1_only_the_course_instructor_may_override(tmp_path):
    _, _, _, gradebook, _ = make_platform(tmp_path)
    other_teacher = User("t2", "Dr. Moss", Role.INSTRUCTOR)
    with pytest.raises(PermissionError):
        gradebook.override_score(other_teacher, "s1", "PY101-final", 10)
    assert gradebook.best("s1", "PY101-final") is None


def test_keep_course_instructor_may_override(tmp_path):
    _, _, _, gradebook, _ = make_platform(tmp_path)
    own_teacher = User("t1", "Dr. Lane", Role.INSTRUCTOR)
    assert gradebook.override_score(own_teacher, "s1", "PY101-final", 7).score == 7
    student = User("s2", "Sid", Role.STUDENT)
    with pytest.raises(PermissionError):
        gradebook.override_score(student, "s1", "PY101-final", 10)


def test_keep_explicit_prerequisite_lists_are_independent():
    catalog = Catalog()
    catalog.add_course("A", "A", 5, "t1", prerequisites=[])
    catalog.add_course("B", "B", 5, "t1", prerequisites=[])
    catalog.add_prerequisite("B", "A")
    assert catalog.course("A").prerequisites == []


def test_keep_waitlisted_student_can_leave_queue(tmp_path):
    _, registrar, *_ = make_platform(tmp_path)
    registrar.enroll("a", "PY101")
    registrar.enroll("b", "PY101")
    registrar.enroll("c", "PY101")
    assert registrar.drop("b", "PY101") is None
    assert registrar.waitlist("PY101") == ["c"]


def test_keep_certificate_name_stays_inside_directory(tmp_path):
    catalog, registrar, tracker, gradebook, issuer = make_platform(tmp_path)
    student = "../../evil"
    registrar.enroll(student, "PY101")
    for lesson in ("intro", "loops"):
        tracker.complete_lesson(student, "PY101", lesson)
    gradebook.submit("PY101-final", student, {i: i % 2 for i in range(10)})
    path = issuer.issue(student, "Eve", "PY101", date(2026, 6, 1))
    assert path.parent == tmp_path.resolve()
    assert path.exists()


def test_keep_certificate_requires_passing_quiz(tmp_path):
    _, registrar, tracker, gradebook, issuer = make_platform(tmp_path)
    registrar.enroll("a", "PY101")
    for lesson in ("intro", "loops"):
        tracker.complete_lesson("a", "PY101", lesson)
    answers = {i: i % 2 for i in range(6)}
    gradebook.submit("PY101-final", "a", answers)
    assert not issuer.is_eligible("a", "PY101")
    answers = {i: i % 2 for i in range(7)}
    gradebook.submit("PY101-final", "a", answers)
    assert issuer.is_eligible("a", "PY101")


def test_keep_write_failure_propagates(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    catalog, registrar, tracker, gradebook, _ = make_platform(tmp_path)
    issuer = CertificateIssuer(catalog, registrar, tracker, gradebook, blocker)
    registrar.enroll("a", "PY101")
    for lesson in ("intro", "loops"):
        tracker.complete_lesson("a", "PY101", lesson)
    gradebook.submit("PY101-final", "a", {i: i % 2 for i in range(10)})
    with pytest.raises(OSError):
        issuer.issue("a", "Ann", "PY101", date(2026, 6, 1))
    assert "PY101" not in registrar.completed("a")

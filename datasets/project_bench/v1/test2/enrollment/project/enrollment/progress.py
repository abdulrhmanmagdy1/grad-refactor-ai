"""Lesson progress per student and course."""

from __future__ import annotations

from enrollment.catalog import Catalog
from enrollment.registration import Registrar


class ProgressError(ValueError):
    """Raised when progress is recorded for a lesson or student that does not fit."""


class ProgressTracker:
    """Which lessons each student has finished in each course."""

    def __init__(self, catalog: Catalog, registrar: Registrar) -> None:
        self.catalog = catalog
        self.registrar = registrar
        self._done: dict[tuple[str, str], set[str]] = {}

    def complete_lesson(self, student_id: str, code: str, lesson_id: str) -> None:
        """Mark a lesson finished; only enrolled students and the course's own lessons."""
        course = self.catalog.course(code)
        if lesson_id not in course.lessons:
            raise ProgressError(f"{lesson_id} is not a lesson of {code}")
        if student_id not in self.registrar.enrolled(code):
            raise ProgressError(f"{student_id} is not enrolled in {code}")
        self._done.setdefault((student_id, code), set()).add(lesson_id)

    def finished_lessons(self, student_id: str, code: str) -> set[str]:
        """The lessons of ``code`` the student has finished."""
        return set(self._done.get((student_id, code), set()))

    def percent_complete(self, student_id: str, code: str) -> int:
        """Share of the course's lessons finished, as a whole percent rounded down."""
        total = len(self.catalog.course(code).lessons)
        if total == 0:
            return 0
        return len(self.finished_lessons(student_id, code)) * 100 // total

    def next_lesson(self, student_id: str, code: str) -> str | None:
        """The first lesson, in course order, that the student has not finished yet."""
        done = self.finished_lessons(student_id, code)
        for lesson_id in self.catalog.course(code).lessons:
            if lesson_id not in done:
                return lesson_id
        return None

    def all_lessons_done(self, student_id: str, code: str) -> bool:
        """True when every lesson of a course with at least one lesson is finished."""
        lessons = self.catalog.course(code).lessons
        return bool(lessons) and set(lessons) <= self.finished_lessons(student_id, code)


def _percent_of_lessons(finished: int, total: int) -> float:
    """Share of lessons finished as a percentage with one decimal."""
    if total <= 0:
        return 0.0
    return round(finished / total * 100, 1)

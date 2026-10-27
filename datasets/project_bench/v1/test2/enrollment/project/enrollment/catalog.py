"""The course catalog: courses, their lessons, prerequisites and quizzes."""

from __future__ import annotations

from enrollment.models import Course, Quiz


class CatalogError(LookupError):
    """Raised when a course or quiz does not exist or is defined twice."""


class Catalog:
    """All courses and quizzes on offer, keyed by course code and quiz id."""

    def __init__(self) -> None:
        self._courses: dict[str, Course] = {}
        self._quizzes: dict[str, Quiz] = {}

    def add_course(
        self,
        code: str,
        title: str,
        capacity: int,
        instructor_id: str,
        prerequisites: list[str] = [],
    ) -> Course:
        """Create a course; every prerequisite must already be in the catalog."""
        if code in self._courses:
            raise CatalogError(f"course {code} already exists")
        for required in prerequisites:
            self.course(required)
        course = Course(code, title, capacity, instructor_id, prerequisites)
        self._courses[code] = course
        return course

    def add_prerequisite(self, code: str, required: str) -> None:
        """Require ``required`` to be completed before enrolling in ``code``."""
        self.course(required)
        course = self.course(code)
        if required not in course.prerequisites:
            course.prerequisites.append(required)

    def add_lesson(self, code: str, lesson_id: str) -> None:
        """Append a lesson to the end of a course."""
        self.course(code).lessons.append(lesson_id)

    def add_quiz(self, quiz: Quiz) -> None:
        """Attach a quiz to its course."""
        self.course(quiz.course_code)
        if quiz.quiz_id in self._quizzes:
            raise CatalogError(f"quiz {quiz.quiz_id} already exists")
        self._quizzes[quiz.quiz_id] = quiz

    def course(self, code: str) -> Course:
        """Return the course with ``code`` or raise CatalogError."""
        try:
            return self._courses[code]
        except KeyError:
            raise CatalogError(f"no course {code}") from None

    def quiz(self, quiz_id: str) -> Quiz:
        """Return the quiz with ``quiz_id`` or raise CatalogError."""
        try:
            return self._quizzes[quiz_id]
        except KeyError:
            raise CatalogError(f"no quiz {quiz_id}") from None

    def courses(self) -> list[Course]:
        """Every course, in the order it was added."""
        return list(self._courses.values())

    def quizzes_for(self, code: str) -> list[Quiz]:
        """The quizzes of a course, in the order they were added."""
        return [quiz for quiz in self._quizzes.values() if quiz.course_code == code]

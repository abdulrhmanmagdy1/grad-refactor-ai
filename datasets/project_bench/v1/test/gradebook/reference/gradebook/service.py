"""The term's grade book: enrolments, recorded scores and published letters."""

from __future__ import annotations

from gradebook.grading import letter_grade, quiz_average, weighted_percentage
from gradebook.models import Course, CourseResult

QUIZZES = "Quizzes"


class GradeBook:
    """Courses, enrolments and recorded scores for one term.

    Only a course's instructor may record, change or publish its grades, and
    every recorded score is kept in ``audit_log`` with the user who entered it.
    """

    def __init__(self, term: str) -> None:
        self.term = term
        self.audit_log: list[tuple[str, str, str, str, float]] = []
        self._courses: dict[str, Course] = {}
        self._enrolled: dict[str, set[str]] = {}
        self._scores: dict[tuple[str, str], dict[str, float]] = {}
        self._published: dict[str, dict[str, CourseResult]] = {}

    def add_course(self, course: Course) -> None:
        """Offer ``course`` this term; course codes are unique."""
        if course.code in self._courses:
            raise ValueError(f"{course.code} is already offered this term")
        self._courses[course.code] = course
        self._enrolled[course.code] = set()

    def enroll(self, course_code: str, student_id: str) -> None:
        """Enrol a student on a course."""
        self._course(course_code)
        self._enrolled[course_code].add(student_id)

    def record_score(
        self, user: str, course_code: str, student_id: str, assessment: str, score: float
    ) -> None:
        """Record an enrolled student's 0-100 score on one of the course's assessments.

        Recording again replaces the earlier score. Nothing can be recorded once
        the course's grades are published.
        """
        course = self._authorised_course(user, course_code)
        self._check_open(course_code, student_id)
        if assessment not in course.assessment_names():
            raise KeyError(f"{course_code} has no assessment called {assessment!r}")
        if not 0 <= score <= 100:
            raise ValueError("scores run from 0 to 100")
        self._scores.setdefault((course_code, student_id), {})[assessment] = float(score)
        self.audit_log.append((user, course_code, student_id, assessment, float(score)))

    def record_quizzes(
        self, user: str, course_code: str, student_id: str, quiz_scores: list[float]
    ) -> None:
        """Record the course's Quizzes assessment from individual quiz scores."""
        self._authorised_course(user, course_code)
        average = round(quiz_average(quiz_scores), 1)
        self.record_score(user, course_code, student_id, QUIZZES, average)

    def scores(self, course_code: str, student_id: str) -> dict[str, float]:
        """A copy of the scores recorded for a student on a course."""
        return dict(self._scores.get((course_code, student_id), {}))

    def percentage(self, course_code: str, student_id: str) -> float:
        """The student's weighted percentage on the course so far."""
        course = self._course(course_code)
        return weighted_percentage(course.assessments, self.scores(course_code, student_id))

    def publish(self, user: str, course_code: str) -> dict[str, CourseResult]:
        """Fix the final letter of every enrolled student and return them by student id."""
        course = self._authorised_course(user, course_code)
        results = {
            student_id: CourseResult(
                self.term,
                course.code,
                course.title,
                course.credits,
                letter_grade(self.percentage(course_code, student_id)),
            )
            for student_id in sorted(self._enrolled[course_code])
        }
        self._published[course_code] = results
        return dict(results)

    def results_for(self, student_id: str) -> list[CourseResult]:
        """The student's published results this term, by course code."""
        return [
            results[student_id]
            for _, results in sorted(self._published.items())
            if student_id in results
        ]

    def _course(self, course_code: str) -> Course:
        """The course offered under ``course_code``; KeyError when there is none."""
        try:
            return self._courses[course_code]
        except KeyError:
            raise KeyError(f"no course {course_code!r} this term") from None

    def _authorised_course(self, user: str, course_code: str) -> Course:
        """The course, provided ``user`` is its instructor; PermissionError otherwise."""
        course = self._course(course_code)
        if course.instructor != user:
            raise PermissionError(f"{user} does not teach {course_code}")
        return course

    def _check_open(self, course_code: str, student_id: str) -> None:
        """Refuse changes for students not enrolled or courses already published."""
        if student_id not in self._enrolled[course_code]:
            raise KeyError(f"{student_id} is not enrolled on {course_code}")
        if course_code in self._published:
            raise ValueError(f"grades for {course_code} are already published")

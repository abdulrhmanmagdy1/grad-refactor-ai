"""Records for students, courses and final results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Student:
    """A student on the school's roll."""

    student_id: str
    name: str
    programme: str


@dataclass(frozen=True)
class Assessment:
    """A graded piece of work and its weight in the course mark."""

    name: str
    weight: float


class Course:
    """A course offering: its credits, its instructor and its weighted assessments."""

    def __init__(
        self,
        code: str,
        title: str,
        credits: int,
        instructor: str,
        assessments: list[Assessment] | None = None,
    ) -> None:
        if credits < 0:
            raise ValueError("credits cannot be negative")
        self.code = code
        self.title = title
        self.credits = credits
        self.instructor = instructor
        self.assessments = list(assessments) if assessments is not None else []

    def add_assessment(self, assessment: Assessment) -> None:
        """Add an assessment to this course; names are unique within a course."""
        if assessment.weight <= 0:
            raise ValueError("an assessment needs a positive weight")
        if assessment.name in self.assessment_names():
            raise ValueError(f"{self.code} already has an assessment called {assessment.name}")
        self.assessments.append(assessment)

    def assessment_names(self) -> set[str]:
        """Names of this course's assessments."""
        return {assessment.name for assessment in self.assessments}

    def __repr__(self) -> str:
        """Short form used in logs and test failures."""
        return f"Course({self.code!r}, {self.title!r}, credits={self.credits})"


@dataclass(frozen=True)
class CourseResult:
    """A final result on a student's record.

    ``letter`` is A to F, or W for a withdrawal and P for a pass in a pass/fail
    course. Term codes such as "2025-2" sort in chronological order.
    """

    term: str
    course_code: str
    title: str
    credits: int
    letter: str

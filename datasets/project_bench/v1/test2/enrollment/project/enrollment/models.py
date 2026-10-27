"""Data types shared by the platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(Enum):
    """What a platform user is allowed to do."""

    STUDENT = "student"
    INSTRUCTOR = "instructor"


@dataclass(frozen=True)
class User:
    """A person with an account on the platform."""

    user_id: str
    name: str
    role: Role


@dataclass
class Course:
    """A course with a seat limit, taught by one instructor.

    ``prerequisites`` holds the codes of courses a student must have completed first,
    and ``lessons`` the lesson ids in teaching order.
    """

    code: str
    title: str
    capacity: int
    instructor_id: str
    prerequisites: list[str]
    lessons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Question:
    """A multiple-choice question; ``answer`` is the index of the correct choice."""

    prompt: str
    choices: tuple[str, ...]
    answer: int
    points: int = 1


@dataclass
class Quiz:
    """A graded quiz that belongs to a course."""

    quiz_id: str
    course_code: str
    questions: list[Question]

    @property
    def max_score(self) -> int:
        """Points available when every question is answered correctly."""
        return sum(question.points for question in self.questions)


@dataclass(frozen=True)
class QuizResult:
    """The score one student obtained on one attempt at a quiz."""

    quiz_id: str
    student_id: str
    score: int
    max_score: int

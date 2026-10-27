"""Quiz grading and the gradebook of results."""

from __future__ import annotations

from enrollment.catalog import Catalog
from enrollment.models import Quiz, QuizResult, Role, User

PASS_PERCENT = 70


def grade(quiz: Quiz, student_id: str, answers: dict[int, int]) -> QuizResult:
    """Score an attempt; ``answers`` maps question index to the chosen choice index.

    Unanswered questions and answers to unknown questions score nothing.
    """
    score = 0
    for index, question in enumerate(quiz.questions):
        if answers.get(index) == question.answer:
            score += question.points
    return QuizResult(quiz.quiz_id, student_id, score, quiz.max_score)


def is_passing(result: QuizResult) -> bool:
    """A result passes when it reaches PASS_PERCENT of the available points."""
    return result.score * 100 >= PASS_PERCENT * result.max_score


class Gradebook:
    """Every recorded quiz result, with the best attempt per student and quiz."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self._results: dict[tuple[str, str], list[QuizResult]] = {}

    def submit(self, quiz_id: str, student_id: str, answers: dict[int, int]) -> QuizResult:
        """Grade an attempt and keep it."""
        result = grade(self.catalog.quiz(quiz_id), student_id, answers)
        self._results.setdefault((student_id, quiz_id), []).append(result)
        return result

    def attempts(self, student_id: str, quiz_id: str) -> list[QuizResult]:
        """All attempts of a student at a quiz, oldest first."""
        return list(self._results.get((student_id, quiz_id), []))

    def best(self, student_id: str, quiz_id: str) -> QuizResult | None:
        """The highest-scoring attempt, or None when the student never tried."""
        attempts = self._results.get((student_id, quiz_id))
        if not attempts:
            return None
        return max(attempts, key=lambda result: result.score)

    def override_score(self, actor: User, student_id: str, quiz_id: str, score: int) -> QuizResult:
        """Record a manual score, for example after a regrade request.

        Only the instructor who teaches the quiz's course may override a score.
        """
        quiz = self.catalog.quiz(quiz_id)
        if actor.role is not Role.INSTRUCTOR:
            raise PermissionError(f"{actor.user_id} may not change grades")
        if not 0 <= score <= quiz.max_score:
            raise ValueError(f"score must be between 0 and {quiz.max_score}")
        result = QuizResult(quiz_id, student_id, score, quiz.max_score)
        self._results.setdefault((student_id, quiz_id), []).append(result)
        return result

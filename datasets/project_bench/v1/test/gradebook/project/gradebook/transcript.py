"""Transcripts: a student's results by term, with credits and GPAs."""

from __future__ import annotations

from collections.abc import Iterable

from gradebook import gpa
from gradebook.models import CourseResult, Student

NO_CREDIT_LETTERS = frozenset({"F", "W"})


def by_term(results: Iterable[CourseResult]) -> dict[str, list[CourseResult]]:
    """Results grouped by term, terms in chronological order, courses by code."""
    grouped: dict[str, list[CourseResult]] = {}
    for result in sorted(results, key=lambda item: (item.term, item.course_code)):
        grouped.setdefault(result.term, []).append(result)
    return grouped


def credits_earned(results: Iterable[CourseResult]) -> int:
    """Credits of the courses passed: every letter except F and W earns its credits."""
    return sum(result.credits for result in results if result.letter not in NO_CREDIT_LETTERS)


def render_transcript(student: Student, results: list[CourseResult], issued_on: str) -> str:
    """Plain-text transcript: a header, one block per term and a closing summary."""
    width = 66
    lines = []
    lines.append("=" * width)
    lines.append("ACADEMIC TRANSCRIPT".center(width))
    lines.append("=" * width)
    lines.append(f"Student:    {student.name}")
    lines.append(f"Student id: {student.student_id}")
    lines.append(f"Programme:  {student.programme}")
    lines.append(f"Issued on:  {issued_on}")
    lines.append("-" * width)
    if not results:
        lines.append("No results on record.")
        lines.append("=" * width)
        return "\n".join(lines)
    total_attempted = 0
    total_earned = 0
    withdrawals = 0
    for term, term_results in by_term(results).items():
        lines.append(f"Term {term}")
        lines.append(f"  {'Code':<10}{'Title':<36}{'Credits':>9}{'Grade':>7}")
        term_attempted = 0
        term_earned = 0
        for result in term_results:
            title = result.title
            if len(title) > 34:
                title = title[:33] + "~"
            lines.append(
                f"  {result.course_code:<10}{title:<36}{result.credits:>9}{result.letter:>7}"
            )
            term_attempted += result.credits
            if result.letter not in NO_CREDIT_LETTERS:
                term_earned += result.credits
            if result.letter == "W":
                withdrawals += 1
        term_gpa = gpa.grade_point_average(term_results)
        lines.append(f"  Credits earned {term_earned} of {term_attempted}, term GPA {term_gpa:.2f}")
        lines.append("")
        total_attempted += term_attempted
        total_earned += term_earned
    cumulative = gpa.grade_point_average(results)
    lines.append("-" * width)
    lines.append(f"Credits attempted: {total_attempted}")
    lines.append(f"Credits earned:    {total_earned}")
    if withdrawals:
        lines.append(f"Withdrawals:       {withdrawals}")
    lines.append(f"Cumulative GPA:    {cumulative:.2f}")
    lines.append(f"Standing:          {gpa.academic_standing(cumulative)}")
    lines.append("=" * width)
    lines.append("End of transcript".center(width))
    return "\n".join(lines)

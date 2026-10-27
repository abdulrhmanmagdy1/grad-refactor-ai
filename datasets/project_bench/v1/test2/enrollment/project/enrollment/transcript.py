"""Plain-text transcripts of a student's courses."""

from __future__ import annotations

from enrollment.catalog import Catalog
from enrollment.progress import ProgressTracker
from enrollment.quizzes import Gradebook, is_passing
from enrollment.registration import Registrar


def build_transcript(
    student_id: str,
    catalog: Catalog,
    registrar: Registrar,
    tracker: ProgressTracker,
    gradebook: Gradebook,
) -> str:
    """Return a transcript listing every course the student is in, waiting for or completed.

    Each course shows its status, lesson progress and the best score of each quiz,
    followed by totals for the student.
    """
    completed = registrar.completed(student_id)
    lines = [f"Transcript for {student_id}", ""]
    course_count = 0
    quiz_count = 0
    passed_count = 0
    for course in catalog.courses():
        if course.code in completed:
            status = "completed"
        elif student_id in registrar.enrolled(course.code):
            status = "enrolled"
        elif student_id in registrar.waitlist(course.code):
            status = "waitlisted"
        else:
            continue
        course_count += 1
        lines.append(f"{course.code} {course.title} [{status}]")
        if status == "waitlisted":
            position = registrar.waitlist(course.code).index(student_id) + 1
            lines.append(f"  waitlist position: {position}")
            lines.append("")
            continue
        total_lessons = len(course.lessons)
        finished = len(tracker.finished_lessons(student_id, course.code))
        percent = tracker.percent_complete(student_id, course.code)
        lines.append(f"  lessons: {finished}/{total_lessons} ({percent}%)")
        next_lesson = tracker.next_lesson(student_id, course.code)
        if next_lesson is not None:
            lines.append(f"  next lesson: {next_lesson}")
        quizzes = catalog.quizzes_for(course.code)
        if not quizzes:
            lines.append("  quizzes: none")
        for quiz in quizzes:
            quiz_count += 1
            best = gradebook.best(student_id, quiz.quiz_id)
            if best is None:
                lines.append(f"  quiz {quiz.quiz_id}: not attempted")
                continue
            attempts = len(gradebook.attempts(student_id, quiz.quiz_id))
            verdict = "pass" if is_passing(best) else "fail"
            if verdict == "pass":
                passed_count += 1
            lines.append(
                f"  quiz {quiz.quiz_id}: {best.score}/{best.max_score} {verdict}"
                f" ({attempts} attempt{'s' if attempts != 1 else ''})"
            )
        lines.append("")
    if course_count == 0:
        lines.append("No courses.")
        return "\n".join(lines)
    lines.append(f"Courses: {course_count}, completed: {len(completed)}")
    lines.append(f"Quizzes passed: {passed_count}/{quiz_count}")
    return "\n".join(lines)

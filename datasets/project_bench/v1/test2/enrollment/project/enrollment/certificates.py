"""Completion certificates, written as text files."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from enrollment.catalog import Catalog
from enrollment.progress import ProgressTracker
from enrollment.quizzes import Gradebook
from enrollment.registration import Registrar

logger = logging.getLogger(__name__)


class CertificateError(Exception):
    """Raised when a certificate cannot be issued."""


def certificate_path(directory: Path, student_id: str, code: str) -> Path:
    """Where a certificate is stored: a file inside ``directory`` named after student and course."""
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", f"{student_id}-{code}")
    path = (directory / f"{safe_name}.txt").resolve()
    if not path.is_relative_to(directory.resolve()):
        raise CertificateError(f"refusing to write a certificate outside {directory}")
    return path


class CertificateIssuer:
    """Checks completion and issues certificates into one directory."""

    def __init__(
        self,
        catalog: Catalog,
        registrar: Registrar,
        tracker: ProgressTracker,
        gradebook: Gradebook,
        directory: Path,
    ) -> None:
        self.catalog = catalog
        self.registrar = registrar
        self.tracker = tracker
        self.gradebook = gradebook
        self.directory = directory

    def quizzes_passed(self, student_id: str, code: str) -> bool:
        """True when the student's best attempt at every quiz of the course passes."""
        for quiz in self.catalog.quizzes_for(code):
            best = self.gradebook.best(student_id, quiz.quiz_id)
            if best is None or best.score * 100 < 70 * best.max_score:
                return False
        return True

    def is_eligible(self, student_id: str, code: str) -> bool:
        """Enrolled, every lesson finished and every quiz of the course passed."""
        return (
            student_id in self.registrar.enrolled(code)
            and self.tracker.all_lessons_done(student_id, code)
            and self.quizzes_passed(student_id, code)
        )

    def issue(self, student_id: str, student_name: str, code: str, on: date) -> Path:
        """Write the certificate file and record the course as completed."""
        if not self.is_eligible(student_id, code):
            raise CertificateError(f"{student_id} has not completed {code}")
        course = self.catalog.course(code)
        text = (
            "Certificate of completion\n\n"
            f"{student_name}\n"
            f"completed {course.title} ({course.code})\n"
            f"on {on.isoformat()}\n"
        )
        path = certificate_path(self.directory, student_id, code)
        try:
            path.write_text(text, encoding="utf-8")
        except Exception:
            logger.exception("could not write certificate %s", path)
            raise
        self.registrar.record_completion(student_id, code)
        return path

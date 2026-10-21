"""Importing score sheets exported from the school's spreadsheet."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from pathlib import Path

from gradebook.service import GradeBook

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("student_id", "assessment", "score")


class ScoreImporter:
    """Feeds score sheets into a grade book on behalf of one user.

    A sheet whose exact contents were imported before is skipped, so uploading
    the same export twice does not record anything twice.
    """

    def __init__(self, book: GradeBook, user: str) -> None:
        self._book = book
        self._user = user
        self._imported: set[str] = set()

    def import_text(self, course_code: str, text: str) -> int:
        """Import ``student_id,assessment,score`` rows and return how many were recorded."""
        fingerprint = hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()
        if fingerprint in self._imported:
            logger.info("score sheet for %s was already imported", course_code)
            return 0
        rows = parse_sheet(text)
        for student_id, assessment, score in rows:
            self._book.record_score(self._user, course_code, student_id, assessment, score)
        self._imported.add(fingerprint)
        return len(rows)

    def import_file(self, course_code: str, path: Path) -> int:
        """Import a sheet saved as a UTF-8 CSV file."""
        return self.import_text(course_code, path.read_text(encoding="utf-8"))


def parse_sheet(text: str) -> list[tuple[str, str, float]]:
    """Rows of a score sheet as (student id, assessment, score); ValueError on a bad sheet."""
    reader = csv.DictReader(io.StringIO(text))
    missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"the sheet has no column {', '.join(missing)}")
    rows = []
    for line_number, row in enumerate(reader, start=2):
        try:
            score = float(row["score"])
        except ValueError:
            raise ValueError(f"line {line_number}: {row['score']!r} is not a score") from None
        rows.append((row["student_id"].strip(), row["assessment"].strip(), score))
    return rows

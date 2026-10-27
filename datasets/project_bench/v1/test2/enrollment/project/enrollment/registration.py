"""Enrollment, waitlists and the record of completed courses."""

from __future__ import annotations

from enum import Enum

from enrollment.catalog import Catalog
from enrollment.models import Course


class EnrollmentError(Exception):
    """Raised when a student cannot enroll in or drop a course."""


class Placement(Enum):
    """Where an enrollment request ended up."""

    ENROLLED = "enrolled"
    WAITLISTED = "waitlisted"


class Registrar:
    """Who is enrolled in, waiting for, or has completed each course."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self._enrolled: dict[str, list[str]] = {}
        self._waitlists: dict[str, list[str]] = {}
        self._completed: dict[str, set[str]] = {}

    def enrolled(self, code: str) -> list[str]:
        """Students enrolled in ``code``, in the order they got a seat."""
        return list(self._enrolled.get(code, []))

    def waitlist(self, code: str) -> list[str]:
        """Students waiting for a seat in ``code``, first come first served."""
        return list(self._waitlists.get(code, []))

    def completed(self, student_id: str) -> set[str]:
        """Codes of the courses the student has completed."""
        return set(self._completed.get(student_id, set()))

    def record_completion(self, student_id: str, code: str) -> None:
        """Remember that the student completed ``code``."""
        self._completed.setdefault(student_id, set()).add(code)

    def _has_prerequisites(self, student_id: str, course: Course) -> bool:
        """True when the student has completed every prerequisite of ``course``."""
        done = self.completed(student_id)
        if not course.prerequisites:
            return True
        return any(required in done for required in course.prerequisites)

    def enroll(self, student_id: str, code: str) -> Placement:
        """Give the student a seat, or a waitlist place when the course is full.

        Refuses students who are already enrolled or waiting, and students missing a
        prerequisite.
        """
        course = self.catalog.course(code)
        seats = self._enrolled.setdefault(code, [])
        queue = self._waitlists.setdefault(code, [])
        if student_id in seats or student_id in queue:
            raise EnrollmentError(f"{student_id} is already registered for {code}")
        if not self._has_prerequisites(student_id, course):
            raise EnrollmentError(f"{student_id} has not completed the prerequisites of {code}")
        if len(seats) < course.capacity:
            seats.append(student_id)
            return Placement.ENROLLED
        queue.append(student_id)
        return Placement.WAITLISTED

    def drop(self, student_id: str, code: str) -> str | None:
        """Remove the student from the course or its waitlist.

        When an enrolled student drops, the student who has waited longest gets the
        seat. Returns the id of the promoted student, if any.
        """
        seats = self._enrolled.get(code, [])
        queue = self._waitlists.get(code, [])
        if student_id in queue:
            queue.remove(student_id)
            return None
        if student_id not in seats:
            raise EnrollmentError(f"{student_id} is not registered for {code}")
        seats.remove(student_id)
        if not queue:
            return None
        promoted = queue.pop()
        seats.append(promoted)
        return promoted

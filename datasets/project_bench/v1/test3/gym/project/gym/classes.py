"""Group classes: the timetable, bookings, capacity and waitlists."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime


class BookingError(Exception):
    """Raised when a class booking or cancellation is not allowed."""


@dataclass
class GymClass:
    """One session of a group class.

    At most ``capacity`` members are booked. Members who ask for a place in a
    full class join the waitlist; when a booked member cancels, the member who
    has been waiting the longest gets the free place.
    """

    class_id: str
    title: str
    starts_at: datetime
    capacity: int
    booked: list[str] = field(default_factory=list)
    waitlist: list[str] = field(default_factory=list)

    @property
    def is_full(self) -> bool:
        """True when every place is taken."""
        return len(self.booked) >= self.capacity

    def book(self, member_id: str) -> str:
        """Book a place, or join the waitlist; returns ``"booked"`` or ``"waitlisted"``."""
        if member_id in self.booked or member_id in self.waitlist:
            raise BookingError(f"{member_id} is already on {self.class_id}")
        if self.is_full:
            self.waitlist.append(member_id)
            return "waitlisted"
        self.booked.append(member_id)
        return "booked"

    def cancel(self, member_id: str) -> str | None:
        """Give up a place or a waitlist spot; returns the member promoted, if any."""
        if member_id in self.waitlist:
            self.waitlist.remove(member_id)
            return None
        if member_id not in self.booked:
            raise BookingError(f"{member_id} is not on {self.class_id}")
        self.booked.remove(member_id)
        if not self.waitlist:
            return None
        promoted = self.waitlist.pop()
        self.booked.append(promoted)
        return promoted

    def drop_lapsed(self, is_active: Callable[[str], bool]) -> list[str]:
        """Remove waitlisted members whose membership is no longer active."""
        removed = []
        for member_id in list(self.waitlist):
            if not is_active(member_id):
                self.waitlist.remove(member_id)
                removed.append(member_id)
        return removed


class Schedule:
    """The timetable of class sessions, keyed by class id."""

    def __init__(self) -> None:
        self.classes: dict[str, GymClass] = {}

    def add(self, gym_class: GymClass) -> None:
        """Add a session; class ids are unique and capacity must be positive."""
        if gym_class.class_id in self.classes:
            raise BookingError(f"class {gym_class.class_id} already exists")
        if gym_class.capacity <= 0:
            raise BookingError("capacity must be positive")
        self.classes[gym_class.class_id] = gym_class

    def get(self, class_id: str) -> GymClass:
        """Return the session with this id."""
        try:
            return self.classes[class_id]
        except KeyError:
            raise BookingError(f"unknown class {class_id}") from None

    def in_month(self, year: int, month: int) -> list[GymClass]:
        """Sessions that start in the given month, earliest first."""
        found = [
            c
            for c in self.classes.values()
            if (c.starts_at.year, c.starts_at.month) == (year, month)
        ]
        return sorted(found, key=lambda c: c.starts_at)

    def version_tag(self) -> str:
        """A short fingerprint of the timetable, so the app can tell whether it changed.

        Bookings do not change the tag; adding a session or moving one does.
        """
        digest = hashlib.md5(usedforsecurity=False)
        for gym_class in sorted(self.classes.values(), key=lambda c: c.class_id):
            row = f"{gym_class.class_id}|{gym_class.starts_at.isoformat()}|{gym_class.capacity}"
            digest.update(row.encode("utf-8"))
        return digest.hexdigest()[:12]

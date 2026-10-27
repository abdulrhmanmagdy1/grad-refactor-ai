"""Planned activities and the reminders for them."""

from __future__ import annotations

from datetime import datetime, timedelta

from crm.models import Activity

ACTIVITY_KINDS = frozenset({"call", "email", "meeting"})


class ActivityLog:
    """Activities planned with contacts."""

    def __init__(self) -> None:
        self.activities: dict[str, Activity] = {}

    def schedule(self, contact_id: str, kind: str, due: datetime, note: str = "") -> Activity:
        """Plan an activity with a contact."""
        if kind not in ACTIVITY_KINDS:
            raise ValueError(f"unknown activity kind {kind!r}")
        activity = Activity(f"A{len(self.activities) + 1}", contact_id, kind, due, note)
        self.activities[activity.activity_id] = activity
        return activity

    def complete(self, activity_id: str) -> None:
        """Mark an activity as done; done activities send no reminders."""
        self.activities[activity_id].done = True

    def due_reminders(
        self, within: timedelta = timedelta(hours=24), now: datetime | None = None
    ) -> list[Activity]:
        """Return open activities due before ``now + within``, earliest first.

        Overdue activities are included. ``now`` defaults to the current time
        at the moment of the call.
        """
        current = datetime.now() if now is None else now
        limit = current + within
        due = [a for a in self.activities.values() if not a.done and a.due <= limit]
        return sorted(due, key=lambda a: a.due)

    def overdue(self, now: datetime | None = None) -> list[Activity]:
        """Return open activities whose due time has passed, earliest first."""
        current = datetime.now() if now is None else now
        late = [a for a in self.activities.values() if not a.done and a.due < current]
        return sorted(late, key=lambda a: a.due)

    def for_contact(self, contact_id: str) -> list[Activity]:
        """Return every activity planned with one contact, earliest first."""
        found = [a for a in self.activities.values() if a.contact_id == contact_id]
        return sorted(found, key=lambda a: a.due)

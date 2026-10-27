"""Tickets, comments, attachments and agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum


class Priority(IntEnum):
    """Ticket priority; a lower number is more urgent."""

    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4

    def raised(self) -> Priority:
        """The next more urgent priority; CRITICAL stays CRITICAL."""
        return Priority(min(self + 1, Priority.LOW))


class Status(Enum):
    """Where a ticket is in its life."""

    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting_on_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"


TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.NEW: frozenset({Status.ASSIGNED}),
    Status.ASSIGNED: frozenset({Status.IN_PROGRESS, Status.RESOLVED}),
    Status.IN_PROGRESS: frozenset({Status.WAITING, Status.RESOLVED}),
    Status.WAITING: frozenset({Status.IN_PROGRESS, Status.RESOLVED}),
    Status.RESOLVED: frozenset({Status.CLOSED, Status.IN_PROGRESS}),
    Status.CLOSED: frozenset(),
}
"""Allowed status changes; RESOLVED -> IN_PROGRESS is a reopen."""


@dataclass(frozen=True)
class Attachment:
    """A file stored for a comment."""

    filename: str
    path: str
    size: int


@dataclass
class Comment:
    """A message on a ticket; internal comments are hidden from the requester."""

    author: str
    body: str
    created_at: datetime
    internal: bool = False
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class Ticket:
    """A support request."""

    id: int
    title: str
    category: str
    priority: Priority
    requester: str
    created_at: datetime
    status: Status = Status.NEW
    assignee: str | None = None
    first_response_at: datetime | None = None
    resolved_at: datetime | None = None
    escalations: int = 0
    comments: list[Comment] = field(default_factory=list)
    history: list[tuple[datetime, Status]] = field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        """True once the ticket is resolved or closed."""
        return self.status in (Status.RESOLVED, Status.CLOSED)

    def move_to(self, status: Status, at: datetime) -> None:
        """Change the status if ``TRANSITIONS`` allows it and record it in the history.

        Resolving sets ``resolved_at``; reopening clears it.
        """
        if status not in TRANSITIONS[self.status]:
            raise ValueError(f"ticket {self.id}: cannot go from {self.status.value} to {status.value}")
        self.status = status
        self.history.append((at, status))
        if status is Status.RESOLVED:
            self.resolved_at = at
        elif status is Status.IN_PROGRESS:
            self.resolved_at = None


@dataclass
class Agent:
    """A support agent, the categories they can handle and their current load."""

    username: str
    skills: frozenset[str]
    max_open: int = 5
    open_tickets: int = 0

    @property
    def has_capacity(self) -> bool:
        """True while the agent holds fewer than ``max_open`` tickets."""
        return self.open_tickets < self.max_open

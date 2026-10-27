"""The helpdesk service: the single entry point used by the web views."""

from __future__ import annotations

import itertools
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from helpdesk.assignment import AssignmentBoard
from helpdesk.attachments import UploadStore
from helpdesk.escalation import Escalator
from helpdesk.models import Agent, Attachment, Comment, Priority, Status, Ticket
from helpdesk.report import PriorityRow, sla_report

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewTicket:
    """What a requester fills in on the support form."""

    title: str
    category: str
    priority: Priority
    requester: str


@dataclass(frozen=True)
class NewComment:
    """A comment as submitted, with its uploaded files as (file name, content) pairs."""

    author: str
    body: str
    files: Sequence[tuple[str, bytes]] = ()
    internal: bool = False


class Helpdesk:
    """Tickets, agents, escalation timers and the uploads folder of one helpdesk."""

    def __init__(self, agents: Iterable[Agent], uploads_root: Path) -> None:
        self.board = AssignmentBoard(agents)
        self.uploads = UploadStore(uploads_root)
        self.escalator = Escalator(on_escalate=self._log_escalation)
        self.tickets: dict[int, Ticket] = {}
        self._ids = itertools.count(1)

    def ticket(self, ticket_id: int) -> Ticket:
        """Return the ticket with ``ticket_id``; an unknown id raises ``KeyError``."""
        return self.tickets[ticket_id]

    def open_ticket(self, request: NewTicket, at: datetime) -> Ticket:
        """Log a new ticket and start its escalation timer.

        The ticket goes straight to the best qualified agent with spare
        capacity; when nobody qualifies it stays NEW for a manual assignment.
        """
        ticket = Ticket(
            id=next(self._ids),
            title=request.title,
            category=request.category,
            priority=request.priority,
            requester=request.requester,
            created_at=at,
        )
        ticket.history.append((at, Status.NEW))
        self.tickets[ticket.id] = ticket
        agent = self.board.pick(ticket.category)
        if agent is not None:
            self.board.assign(ticket, agent.username)
            ticket.move_to(Status.ASSIGNED, at)
        self.escalator.schedule([ticket])
        return ticket

    def assign(self, ticket_id: int, username: str, at: datetime) -> None:
        """Hand a NEW ticket to a named agent."""
        ticket = self.ticket(ticket_id)
        self.board.assign(ticket, username)
        ticket.move_to(Status.ASSIGNED, at)

    def reassign(self, ticket_id: int, username: str) -> None:
        """Move an assigned ticket to another agent."""
        self.board.reassign(self.ticket(ticket_id), username)

    def add_comment(self, ticket_id: int, draft: NewComment, at: datetime) -> Comment:
        """Add a comment and store its attachments.

        The first public comment written by an agent is the ticket's first
        response. If one attachment cannot be stored, those already stored for
        this comment are deleted, the comment is not added and the error is
        passed on to the caller.
        """
        ticket = self.ticket(ticket_id)
        stored: list[Attachment] = []
        try:
            for filename, data in draft.files:
                stored.append(self.uploads.save(ticket.id, filename, data))
        except Exception:
            logger.exception("upload failed on ticket %s; removing %d file(s)", ticket.id, len(stored))
            for attachment in stored:
                self.uploads.delete(attachment)
            raise
        comment = Comment(draft.author, draft.body, at, draft.internal, stored)
        ticket.comments.append(comment)
        if not draft.internal and ticket.first_response_at is None and self._is_agent(draft.author):
            ticket.first_response_at = at
        return comment

    def set_status(self, ticket_id: int, status: Status, at: datetime) -> None:
        """Move a ticket to ``status``.

        Resolving frees the agent's slot and stops the escalation timer;
        reopening a resolved ticket counts it towards the agent's load again.
        """
        ticket = self.ticket(ticket_id)
        was_resolved = ticket.is_resolved
        ticket.move_to(status, at)
        if status is Status.RESOLVED:
            self.board.release(ticket)
            self.escalator.cancel(ticket.id)
        elif was_resolved and status is Status.IN_PROGRESS:
            self.board.take_back(ticket)

    def delete_ticket(self, ticket_id: int) -> int:
        """Remove a closed ticket with its attachments; returns how many files were deleted."""
        ticket = self.ticket(ticket_id)
        if ticket.status is not Status.CLOSED:
            raise ValueError(f"ticket {ticket_id} is not closed")
        del self.tickets[ticket_id]
        return self.uploads.purge_ticket(ticket_id)

    def tick(self, now: datetime) -> int:
        """Advance the escalation clock to ``now``; returns how many timers fired."""
        return self.escalator.tick(now)

    def report(self, now: datetime) -> list[PriorityRow]:
        """The SLA report over every ticket at ``now``."""
        return sla_report(self.tickets.values(), now)

    def _is_agent(self, username: str) -> bool:
        try:
            self.board.agent(username)
        except KeyError:
            return False
        return True

    @staticmethod
    def _log_escalation(ticket: Ticket) -> None:
        logger.warning("ticket %s escalated to %s", ticket.id, ticket.priority.name)

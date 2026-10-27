"""Escalation timers: tickets nobody answered in time move up one priority."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from helpdesk.models import Ticket
from helpdesk.sla import response_deadline


@dataclass(frozen=True)
class Timer:
    """An action to run once at ``fires_at``."""

    ticket_id: int
    fires_at: datetime
    action: Callable[[], None]


class Escalator:
    """Keeps one timer per watched ticket and fires them as the clock moves on.

    A timer fires at the ticket's response deadline. If the ticket still has no
    first response and is not resolved by then, its priority is raised one
    level, its escalation count goes up by one and ``on_escalate`` is called.
    """

    def __init__(self, on_escalate: Callable[[Ticket], None] | None = None) -> None:
        self._timers: list[Timer] = []
        self._on_escalate = on_escalate

    def pending(self) -> list[Timer]:
        """Timers that have not fired yet, soonest first."""
        return sorted(self._timers, key=lambda t: t.fires_at)

    def schedule(self, tickets: Iterable[Ticket]) -> int:
        """Start a timer for each unresolved ticket; returns how many were started."""
        started = 0
        for ticket in tickets:
            if ticket.is_resolved:
                continue
            self._timers.append(
                Timer(ticket.id, response_deadline(ticket), lambda ticket=ticket: self._escalate(ticket))
            )
            started += 1
        return started

    def cancel(self, ticket_id: int) -> None:
        """Drop the timers of one ticket."""
        self._timers = [t for t in self._timers if t.ticket_id != ticket_id]

    def tick(self, now: datetime) -> int:
        """Fire, once, every timer due at or before ``now``; returns how many fired."""
        fired = 0
        for timer in list(self._timers):
            if timer.fires_at <= now:
                self._timers.remove(timer)
                timer.action()
                fired += 1
        return fired

    def _escalate(self, ticket: Ticket) -> None:
        if ticket.first_response_at is not None or ticket.is_resolved:
            return
        ticket.priority = ticket.priority.raised()
        ticket.escalations += 1
        if self._on_escalate is not None:
            self._on_escalate(ticket)

"""Service level targets: how fast each priority must be answered and resolved."""

from __future__ import annotations

from datetime import datetime, timedelta

from helpdesk.models import Priority, Ticket

RESPONSE_TARGETS: dict[Priority, timedelta] = {
    Priority.CRITICAL: timedelta(minutes=30),
    Priority.HIGH: timedelta(hours=2),
    Priority.NORMAL: timedelta(hours=8),
    Priority.LOW: timedelta(hours=24),
}

RESOLUTION_TARGETS: dict[Priority, timedelta] = {
    Priority.CRITICAL: timedelta(hours=4),
    Priority.HIGH: timedelta(hours=24),
    Priority.NORMAL: timedelta(hours=72),
    Priority.LOW: timedelta(hours=120),
}


def response_deadline(ticket: Ticket) -> datetime:
    """When the first agent response is due, measured from creation at the current priority."""
    return ticket.created_at + RESPONSE_TARGETS[ticket.priority]


def resolution_deadline(ticket: Ticket) -> datetime:
    """When the ticket must be resolved, measured from creation at the current priority."""
    return ticket.created_at + RESOLUTION_TARGETS[ticket.priority]


def response_breached(ticket: Ticket, now: datetime) -> bool:
    """True when the first response came after its deadline, or has not come and the deadline passed."""
    answered = ticket.first_response_at if ticket.first_response_at is not None else now
    return answered > response_deadline(ticket)


def resolution_breached(ticket: Ticket, now: datetime) -> bool:
    """True when the ticket was resolved late, or is unresolved and its deadline passed."""
    finished = ticket.resolved_at if ticket.resolved_at is not None else now
    return finished > resolution_deadline(ticket)

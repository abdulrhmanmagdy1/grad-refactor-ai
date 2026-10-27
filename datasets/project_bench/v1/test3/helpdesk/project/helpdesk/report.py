"""The SLA report sent to the IT manager every Monday."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from helpdesk.models import Priority, Ticket

_RESOLUTION_HOURS: dict[Priority, int] = {
    Priority.CRITICAL: 4,
    Priority.HIGH: 24,
    Priority.NORMAL: 72,
    Priority.LOW: 120,
}


@dataclass(frozen=True)
class PriorityRow:
    """SLA figures for one priority."""

    priority: Priority
    tickets: int
    resolved: int
    breached: int

    @property
    def compliance(self) -> float:
        """Percentage of tickets within their resolution target; 100.0 when there are none."""
        if self.tickets == 0:
            return 100.0
        return round(100.0 * (self.tickets - self.breached) / self.tickets, 1)


def _breached(ticket: Ticket, now: datetime) -> bool:
    deadline = ticket.created_at + timedelta(hours=_RESOLUTION_HOURS[ticket.priority])
    finished = ticket.resolved_at if ticket.resolved_at is not None else now
    return finished > deadline


def sla_report(tickets: Iterable[Ticket], now: datetime) -> list[PriorityRow]:
    """One row per priority, most urgent first, counting resolution breaches at ``now``."""
    ticket_list = list(tickets)
    rows = []
    for priority in Priority:
        group = [t for t in ticket_list if t.priority is priority]
        rows.append(
            PriorityRow(
                priority=priority,
                tickets=len(group),
                resolved=sum(1 for t in group if t.resolved_at is not None),
                breached=sum(1 for t in group if _breached(t, now)),
            )
        )
    return rows


def open_breaches_by_agent(tickets: Iterable[Ticket], now: datetime) -> dict[str, list[int]]:
    """Ids of unresolved tickets past their resolution deadline, grouped by assignee.

    Unassigned tickets are listed under ``"unassigned"``; ids are in creation order.
    Housekeeping tickets filed by the ``"helpdesk"`` account itself are left out.
    """
    result: dict[str, list[int]] = {}
    for ticket in sorted(tickets, key=lambda t: t.created_at):
        if ticket.resolved_at is None:
            if ticket.requester != "helpdesk":
                if _breached(ticket, now):
                    if ticket.assignee is not None:
                        if ticket.assignee not in result:
                            result[ticket.assignee] = []
                        result[ticket.assignee].append(ticket.id)
                    else:
                        result.setdefault("unassigned", []).append(ticket.id)
    return result

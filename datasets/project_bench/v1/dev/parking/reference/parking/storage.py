"""The log of closed tickets, kept in SQLite."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from parking.models import Ticket

SORTABLE = ("entered", "exited", "amount", "plate")


class TicketLog:
    """Closed tickets in an SQLite database (in memory unless a path is given)."""

    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS tickets (ticket_id TEXT PRIMARY KEY, plate TEXT,"
            " space TEXT, entered TEXT, exited TEXT, amount REAL)"
        )

    def record(self, ticket: Ticket) -> None:
        """Store a closed ticket."""
        if ticket.exited is None:
            raise ValueError(f"ticket {ticket.ticket_id} is still open")
        row = (
            ticket.ticket_id,
            ticket.plate,
            ticket.space,
            ticket.entered.isoformat(),
            ticket.exited.isoformat(),
            ticket.amount,
        )
        self.db.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)", row)
        self.db.commit()

    def for_plate(self, plate: str) -> list[Ticket]:
        """Every closed ticket of one car, oldest first."""
        query = "SELECT * FROM tickets WHERE plate = ? ORDER BY entered"
        return [to_ticket(row) for row in self.db.execute(query, (plate,))]

    def all(self, order_by: str = "entered") -> list[Ticket]:
        """Every closed ticket, sorted by one of the SORTABLE columns."""
        if order_by not in SORTABLE:
            raise ValueError(f"cannot sort tickets by {order_by!r}")
        query = f"SELECT * FROM tickets ORDER BY {order_by}, ticket_id"
        return [to_ticket(row) for row in self.db.execute(query)]


def to_ticket(row: tuple[str, str, str, str, str, float]) -> Ticket:
    """A ticket from one row of the tickets table."""
    ticket_id, plate, space, entered, exited, amount = row
    return Ticket(
        ticket_id,
        plate,
        space,
        datetime.fromisoformat(entered),
        datetime.fromisoformat(exited),
        amount,
    )

"""The entry and exit barriers: tickets, payment and permits."""

from __future__ import annotations

from datetime import datetime

from parking.garage import Garage
from parking.models import Ticket
from parking.permits import PermitRegistry
from parking.rates import RateCard
from parking.storage import TicketLog

LOST_TICKET_FEE = 20.0


class ParkingDesk:
    """Hands out tickets at the entry and takes payment at the exit."""

    def __init__(
        self, garage: Garage, rates: RateCard, permits: PermitRegistry, log: TicketLog
    ) -> None:
        self.garage = garage
        self.rates = rates
        self.permits = permits
        self.log = log
        self.open: dict[str, Ticket] = {}
        self._next = 1

    def enter(self, plate: str, now: datetime, kind: str = "standard") -> Ticket:
        """Park the car in a free space of its kind and hand out a ticket."""
        space = self.garage.park(plate, kind)
        ticket = Ticket(f"T{self._next:05d}", plate, space.code, now)
        self._next += 1
        self.open[ticket.ticket_id] = ticket
        return ticket

    def quote(self, ticket_id: str, now: datetime) -> float:
        """What the stay costs if the car leaves now; cars with a valid permit pay nothing."""
        ticket = self.open[ticket_id]
        if self.permits.is_valid(ticket.plate, now.date()):
            return 0.0
        return self.rates.charge(ticket.entered, now)

    def leave(self, ticket_id: str, now: datetime, fee: float = 0.0) -> Ticket:
        """Charge the stay plus `fee`, free the space and move the ticket to the log."""
        if ticket_id not in self.open:
            raise KeyError(f"no open ticket {ticket_id}")
        ticket = self.open[ticket_id]
        ticket.amount = self.quote(ticket_id, now) + fee
        ticket.exited = now
        self.garage.leave(ticket.space)
        self.log.record(ticket)
        del self.open[ticket_id]
        return ticket

    def lost_ticket(self, plate: str, now: datetime) -> Ticket:
        """Let out a car whose driver lost the ticket: the stay plus LOST_TICKET_FEE."""
        ticket = next((t for t in self.open.values() if t.plate == plate), None)
        if ticket is None:
            raise LookupError(f"{plate} has no open ticket")
        return self.leave(ticket.ticket_id, now, fee=LOST_TICKET_FEE)

    def receipt(self, ticket: Ticket) -> str:
        """The printed receipt: ticket, plate, times, and the amount with the VAT it includes."""
        if ticket.exited is None:
            raise ValueError(f"ticket {ticket.ticket_id} is still open")
        vat = ticket.amount - ticket.amount / 1.2
        return (
            f"{ticket.ticket_id} {ticket.plate} {ticket.entered:%Y-%m-%d %H:%M}"
            f" - {ticket.exited:%H:%M}  {ticket.amount:.2f} (incl. VAT {vat:.2f})"
        )

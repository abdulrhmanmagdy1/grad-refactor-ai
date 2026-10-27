"""Refund policy: what customers get back, and until when."""

from __future__ import annotations

from datetime import datetime, timedelta

from ticketing import purchase
from ticketing.models import Event, Ticket, TicketStatus

REFUND_CUTOFF = timedelta(hours=48)


class RefundError(Exception):
    """Raised when a ticket cannot be refunded."""


def refund_deadline(event: Event) -> datetime:
    """Last moment a ticket for ``event`` can be refunded: 48 hours before it starts."""
    return event.starts_at - REFUND_CUTOFF


def _find_ticket(office: purchase.TicketOffice, order_id: str, code: str) -> Ticket:
    order = office.orders.get(order_id)
    if order is None:
        raise RefundError(f"unknown order {order_id}")
    for ticket in order.tickets:
        if ticket.code == code:
            return ticket
    raise RefundError(f"order {order_id} has no ticket {code}")


def refund_ticket(
    office: purchase.TicketOffice, order_id: str, code: str, now: datetime
) -> int:
    """Refund one ticket of an order and put its seat back on sale.

    The customer gets back what they paid for the seat; the booking fee is kept.
    Refunds are accepted up to and including the refund deadline.
    Returns the refunded amount in cents.
    """
    ticket = _find_ticket(office, order_id, code)
    if ticket.status is TicketStatus.REFUNDED:
        raise RefundError(f"ticket {code} was already refunded")
    if now > refund_deadline(office.event):
        raise RefundError("the refund window for this event has closed")
    ticket.status = TicketStatus.REFUNDED
    office.seat_map.release_sold(ticket.seat)
    return ticket.paid_cents


def cancel_event(office: purchase.TicketOffice) -> dict[str, int]:
    """Refund everything still valid after the organiser cancels the event.

    Unlike a customer refund, the booking fee of every affected order is returned too.
    Returns the refunded amount per customer, in cents.
    """
    refunded: dict[str, int] = {}
    for order in office.orders.values():
        if order.event_id == office.event.event_id:
            amount = 0
            touched = False
            for ticket in order.tickets:
                if ticket.status is TicketStatus.VALID:
                    ticket.status = TicketStatus.REFUNDED
                    office.seat_map.release_sold(ticket.seat)
                    amount += ticket.paid_cents
                    touched = True
            if touched:
                if order.customer in refunded:
                    refunded[order.customer] += amount + order.booking_fee_cents
                else:
                    refunded[order.customer] = amount + order.booking_fee_cents
    return refunded

"""Checkout: turn a seat hold into a paid order with tickets."""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from datetime import datetime

from ticketing import refunds
from ticketing.models import Event, Order, Ticket
from ticketing.pricing import DiscountBook, apply_discount, tier_for_seat
from ticketing.seating import SeatMap

BOOKING_FEE_CENTS = 150
TICKET_CODE_LENGTH = 10
TICKET_CODE_ALPHABET = string.ascii_uppercase + string.digits


@dataclass(frozen=True)
class Receipt:
    """What the customer sees after paying."""

    order_id: str
    total_cents: int
    seat_labels: list[str]
    refundable_until: datetime


def _ticket_code() -> str:
    """Return a new ticket code; the gate admits whoever presents a valid code."""
    return "".join(random.SystemRandom().choices(TICKET_CODE_ALPHABET, k=TICKET_CODE_LENGTH))


class TicketOffice:
    """Sells the seats of one event."""

    def __init__(self, event: Event, discounts: DiscountBook | None = None) -> None:
        self.event = event
        self.seat_map = SeatMap(event)
        self.discounts = discounts if discounts is not None else DiscountBook()
        self.orders: dict[str, Order] = {}

    def checkout(
        self,
        hold_id: str,
        customer: str,
        now: datetime,
        discount_code: str | None = None,
    ) -> Order:
        """Buy the seats of a live hold, applying ``discount_code`` to every seat.

        One booking fee of BOOKING_FEE_CENTS is charged per order.
        """
        hold = self.seat_map.active_hold(hold_id, customer, now)
        percent_off = 0
        if discount_code is not None:
            percent_off = self.discounts.redeem(discount_code, now).percent_off
        tickets = []
        for seat in sorted(hold.seats, key=lambda s: (s.row, s.number)):
            tier = tier_for_seat(self.event, seat)
            paid = apply_discount(tier.price_cents, percent_off)
            tickets.append(
                Ticket(_ticket_code(), self.event.event_id, seat, tier.name, tier.price_cents, paid)
            )
        self.seat_map.complete(hold)
        order_id = f"ORD-{len(self.orders) + 1:05d}"
        order = Order(
            order_id, customer, self.event.event_id, tickets, BOOKING_FEE_CENTS, discount_code, now
        )
        self.orders[order_id] = order
        return order

    def receipt(self, order_id: str) -> Receipt:
        """Summarise an order for the customer, including the refund deadline."""
        order = self.orders[order_id]
        labels = [ticket.seat.label for ticket in order.tickets]
        deadline = refunds.refund_deadline(self.event)
        return Receipt(order.order_id, order.total_cents, labels, deadline)

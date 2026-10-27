from datetime import datetime, timedelta

import pytest

from ticketing.models import Event, PriceTier, Seat, TicketStatus, Venue
from ticketing.pricing import DiscountBook, DiscountCode, PricingError, apply_discount
from ticketing.purchase import BOOKING_FEE_CENTS, TicketOffice
from ticketing.refunds import RefundError, refund_deadline, refund_ticket
from ticketing.reports import export_orders_csv, sales_by_tier
from ticketing.seating import SeatUnavailableError

NOW = datetime(2026, 5, 1, 12, 0)


def make_office(discounts: DiscountBook | None = None) -> TicketOffice:
    venue = Venue.with_rows("Hall", "ABC", 4)
    tiers = [
        PriceTier("front", frozenset("A"), 5000),
        PriceTier("rear", frozenset("BC"), 3000),
    ]
    event = Event("EV1", "Concert", venue, NOW + timedelta(days=10), tiers)
    return TicketOffice(event, discounts)


def test_hold_and_checkout_charges_tier_price_and_fee():
    office = make_office()
    hold = office.seat_map.hold("ann", [Seat("A", 1), Seat("B", 2)], NOW)
    order = office.checkout(hold.hold_id, "ann", NOW + timedelta(minutes=1))
    assert [t.seat.label for t in order.tickets] == ["A1", "B2"]
    assert order.total_cents == 5000 + 3000 + BOOKING_FEE_CENTS
    assert Seat("A", 1) not in office.seat_map.available(NOW)


def test_held_seat_cannot_be_held_again():
    office = make_office()
    office.seat_map.hold("ann", [Seat("A", 1)], NOW)
    with pytest.raises(SeatUnavailableError):
        office.seat_map.hold("bob", [Seat("A", 1)], NOW + timedelta(minutes=2))


def test_checkout_after_hold_expired_is_refused():
    office = make_office()
    hold = office.seat_map.hold("ann", [Seat("C", 3)], NOW)
    with pytest.raises(SeatUnavailableError):
        office.checkout(hold.hold_id, "ann", NOW + timedelta(minutes=30))


def test_discount_is_applied_to_each_seat():
    book = DiscountBook()
    book.add(DiscountCode("SPRING", 10, 5, NOW + timedelta(days=3)))
    office = make_office(book)
    hold = office.seat_map.hold("ann", [Seat("B", 1)], NOW)
    order = office.checkout(hold.hold_id, "ann", NOW, discount_code="spring")
    assert order.tickets[0].paid_cents == 2700
    assert book.get("SPRING").times_used == 1


def test_expired_discount_is_refused():
    book = DiscountBook()
    book.add(DiscountCode("OLD", 10, 5, NOW - timedelta(days=1)))
    with pytest.raises(PricingError):
        book.redeem("OLD", NOW)


def test_apply_discount_whole_numbers():
    assert apply_discount(2000, 10) == 1800
    assert apply_discount(2000, 0) == 2000


def test_refund_before_deadline_returns_seat_price():
    office = make_office()
    hold = office.seat_map.hold("ann", [Seat("A", 2)], NOW)
    order = office.checkout(hold.hold_id, "ann", NOW)
    code = order.tickets[0].code
    assert refund_ticket(office, order.order_id, code, NOW) == 5000
    assert order.tickets[0].status is TicketStatus.REFUNDED
    assert Seat("A", 2) in office.seat_map.available(NOW)


def test_refund_after_deadline_is_refused():
    office = make_office()
    hold = office.seat_map.hold("ann", [Seat("A", 2)], NOW)
    order = office.checkout(hold.hold_id, "ann", NOW)
    late = refund_deadline(office.event) + timedelta(minutes=1)
    with pytest.raises(RefundError):
        refund_ticket(office, order.order_id, order.tickets[0].code, late)


def test_receipt_lists_seats_and_deadline():
    office = make_office()
    hold = office.seat_map.hold("ann", [Seat("C", 1)], NOW)
    order = office.checkout(hold.hold_id, "ann", NOW)
    receipt = office.receipt(order.order_id)
    assert receipt.seat_labels == ["C1"]
    assert receipt.refundable_until == office.event.starts_at - timedelta(hours=48)


def test_report_counts_sold_seats_per_tier():
    office = make_office()
    hold = office.seat_map.hold("ann", [Seat("A", 1), Seat("C", 4)], NOW)
    office.checkout(hold.hold_id, "ann", NOW)
    lines = sales_by_tier(office.event, list(office.orders.values()))
    assert [(line.tier, line.seats_total, line.seats_sold) for line in lines] == [
        ("front", 4, 1),
        ("rear", 8, 1),
    ]


def test_orders_export_writes_csv(tmp_path):
    office = make_office()
    hold = office.seat_map.hold("ann", [Seat("B", 3)], NOW)
    office.checkout(hold.hold_id, "ann", NOW)
    path = export_orders_csv(list(office.orders.values()), tmp_path)
    assert path.read_text(encoding="utf-8").splitlines()[1] == "ORD-00001,ann,1,31.50"
    assert (tmp_path / "orders.csv.md5").exists()

import hashlib
import random
from datetime import datetime, timedelta

import pytest

from ticketing.models import Event, PriceTier, Seat, Venue
from ticketing.pricing import DiscountBook, DiscountCode, PricingError, apply_discount
from ticketing.purchase import BOOKING_FEE_CENTS, TicketOffice
from ticketing.refunds import cancel_event, refund_ticket
from ticketing.reports import export_sales_csv, sales_by_tier

NOW = datetime(2026, 5, 1, 12, 0)


def make_office(discounts=None):
    venue = Venue.with_rows("Hall", "ABC", 4)
    tiers = [
        PriceTier("front", frozenset("A"), 5000),
        PriceTier("rear", frozenset("BC"), 3000),
    ]
    event = Event("EV1", "Concert", venue, NOW + timedelta(days=10), tiers)
    return TicketOffice(event, discounts)


def buy(office, customer, seats, code=None):
    hold = office.seat_map.hold(customer, seats, NOW)
    return office.checkout(hold.hold_id, customer, NOW, discount_code=code)


def test_B1_discount_rounds_to_nearest_cent():
    assert apply_discount(1995, 15) == 1696
    assert apply_discount(333, 10) == 300


def test_B2_report_revenue_is_what_customers_paid():
    book = DiscountBook()
    book.add(DiscountCode("HALF", 50, 10, NOW + timedelta(days=1)))
    office = make_office(book)
    buy(office, "ann", [Seat("A", 1)], code="HALF")
    buy(office, "bob", [Seat("B", 1)])
    lines = {line.tier: line for line in sales_by_tier(office.event, list(office.orders.values()))}
    assert lines["front"].revenue_cents == 2500
    assert lines["rear"].revenue_cents == 3000


def test_B3_discount_code_stops_at_max_uses():
    book = DiscountBook()
    book.add(DiscountCode("TWICE", 10, 2, NOW + timedelta(days=1)))
    book.redeem("TWICE", NOW)
    book.redeem("TWICE", NOW)
    with pytest.raises(PricingError):
        book.redeem("TWICE", NOW)
    assert book.get("TWICE").times_used == 2


def test_S1_ticket_codes_do_not_follow_the_random_seed():
    codes = []
    for _ in range(2):
        office = make_office()
        hold = office.seat_map.hold("ann", [Seat("A", 1)], NOW)
        random.seed(1234)
        order = office.checkout(hold.hold_id, "ann", NOW)
        codes.append(order.tickets[0].code)
    assert codes[0] != codes[1]


def test_keep_ticket_codes_unique_within_an_order():
    office = make_office()
    order = buy(office, "ann", [Seat("C", n) for n in range(1, 5)])
    assert len({t.code for t in order.tickets}) == 4


def test_keep_release_expired_drops_only_expired_holds():
    office = make_office()
    office.seat_map.hold("ann", [Seat("A", 1)], NOW)
    office.seat_map.hold("bob", [Seat("A", 2)], NOW + timedelta(minutes=5))
    office.seat_map.hold("cat", [Seat("A", 3)], NOW + timedelta(minutes=1))
    dropped = office.seat_map.release_expired(NOW + timedelta(minutes=10))
    assert dropped == 1
    assert office.seat_map.held_seats(NOW + timedelta(minutes=10)) == {Seat("A", 2), Seat("A", 3)}


def test_keep_hold_expires_at_its_deadline():
    office = make_office()
    hold = office.seat_map.hold("ann", [Seat("B", 4)], NOW)
    assert hold.is_expired(hold.expires_at)
    assert not hold.is_expired(hold.expires_at - timedelta(seconds=1))


def test_keep_export_checksum_matches_file(tmp_path):
    office = make_office()
    buy(office, "ann", [Seat("A", 4)])
    lines = sales_by_tier(office.event, list(office.orders.values()))
    path = export_sales_csv(lines, tmp_path)
    expected = hashlib.md5(path.read_bytes()).hexdigest()
    assert (tmp_path / "sales.csv.md5").read_text(encoding="utf-8") == expected


def test_keep_refund_keeps_booking_fee_and_is_once_only():
    office = make_office()
    order = buy(office, "ann", [Seat("B", 2)])
    code = order.tickets[0].code
    assert refund_ticket(office, order.order_id, code, NOW) == 3000
    with pytest.raises(Exception):
        refund_ticket(office, order.order_id, code, NOW)


def test_keep_cancel_event_returns_fees():
    office = make_office()
    buy(office, "ann", [Seat("A", 1)])
    buy(office, "ann", [Seat("B", 1)])
    buy(office, "bob", [Seat("C", 1)])
    assert cancel_event(office) == {
        "ann": 5000 + 3000 + 2 * BOOKING_FEE_CENTS,
        "bob": 3000 + BOOKING_FEE_CENTS,
    }
    assert office.seat_map.sold_seats() == set()


def test_keep_discount_code_is_case_insensitive():
    book = DiscountBook()
    book.add(DiscountCode("Promo", 20, 3, NOW + timedelta(days=1)))
    office = make_office(book)
    order = buy(office, "ann", [Seat("C", 2)], code="PROMO")
    assert order.tickets[0].paid_cents == 2400

from datetime import date
from decimal import Decimal

import pytest

from hotel.cancellation import fee_for
from hotel.invoice import InvoiceArchive, build_invoice
from hotel.rates import RateTable, Season, nights_between
from hotel.reports import daily_summary, revenue_between
from hotel.reservations import ReservationBook, Status
from hotel.rooms import Room, RoomCatalog, RoomType

DOUBLE = RoomType("DBL", "Double", Decimal("100.00"), 2)
SUITE = RoomType("STE", "Suite", Decimal("250.00"), 4)


@pytest.fixture
def catalog() -> RoomCatalog:
    rooms = RoomCatalog()
    rooms.add_type(DOUBLE)
    rooms.add_type(SUITE)
    rooms.add_room(Room("101", DOUBLE, 1))
    rooms.add_room(Room("102", DOUBLE, 1))
    rooms.add_room(Room("201", SUITE, 2))
    return rooms


@pytest.fixture
def book(catalog: RoomCatalog) -> ReservationBook:
    summer = Season("summer", date(2026, 7, 1), date(2026, 8, 31), Decimal("1.5"))
    return ReservationBook(catalog, RateTable([summer]))


def test_nights_exclude_the_check_out_day():
    assert nights_between(date(2026, 3, 1), date(2026, 3, 3)) == [date(2026, 3, 1), date(2026, 3, 2)]
    with pytest.raises(ValueError):
        nights_between(date(2026, 3, 3), date(2026, 3, 3))


def test_stay_price_uses_the_season_of_each_night():
    rates = RateTable([Season("summer", date(2026, 7, 1), date(2026, 8, 31), Decimal("1.5"))])
    assert rates.stay_price(DOUBLE, date(2026, 6, 29), date(2026, 7, 2)) == Decimal("350.00")


def test_reserve_and_refuse_an_overlapping_stay(book: ReservationBook):
    first = book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 4))
    assert first.reference == "R00001"
    assert first.price == Decimal("300.00")
    with pytest.raises(ValueError):
        book.reserve("Bob", "101", date(2026, 3, 2), date(2026, 3, 5))
    assert [room.number for room in book.available_rooms("DBL", date(2026, 3, 2), date(2026, 3, 3))] == ["102"]


def test_out_of_service_room_is_not_available(book: ReservationBook, catalog: RoomCatalog):
    catalog.set_in_service("102", False)
    assert not book.is_available("102", date(2026, 3, 1), date(2026, 3, 2))


def test_cancellation_fees(book: ReservationBook):
    stay = book.reserve("Ada", "101", date(2026, 3, 10), date(2026, 3, 14))
    assert fee_for(stay, date(2026, 3, 1)) == Decimal("0.00")
    assert fee_for(stay, date(2026, 3, 6)) == Decimal("100.00")
    assert fee_for(stay, date(2026, 3, 9)) == Decimal("200.00")
    assert book.cancel(stay.reference, date(2026, 3, 6)) == Decimal("100.00")
    assert stay.status is Status.CANCELLED
    assert book.is_available("101", date(2026, 3, 10), date(2026, 3, 14))


def test_invoice_for_a_stay(book: ReservationBook):
    stay = book.reserve("Ada", "201", date(2026, 3, 1), date(2026, 3, 3))
    invoice = build_invoice(stay)
    assert invoice.subtotal == Decimal("500.00")
    assert invoice.vat == Decimal("70.00")
    assert invoice.total == Decimal("570.00")


def test_archive_round_trip(book: ReservationBook, tmp_path):
    stay = book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 2))
    archive = InvoiceArchive(tmp_path / "invoices")
    invoice = build_invoice(stay)
    archive.store(invoice)
    assert archive.names() == ["INV-R00001.txt"]
    assert "Guest: Ada" in archive.read("INV-R00001.txt")


def test_daily_summary_and_revenue(book: ReservationBook, catalog: RoomCatalog):
    book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 3))
    book.reserve("Bob", "201", date(2026, 3, 2), date(2026, 3, 4))
    summary = daily_summary(catalog, book, date(2026, 3, 2))
    assert summary.arrivals == ["Bob"]
    assert summary.departures == []
    assert summary.occupied_rooms == 2
    assert summary.occupancy == Decimal("66.67")
    assert revenue_between(book, date(2026, 3, 1), date(2026, 3, 31)) == Decimal("700.00")


def test_records_round_trip(book: ReservationBook, catalog: RoomCatalog):
    book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 3), special_requests=["cot"])
    copy = ReservationBook(catalog, RateTable())
    assert copy.restore(book.records()) == 1
    restored = copy.get("R00001")
    assert restored.special_requests == ["cot"]
    assert copy.reserve("Bob", "102", date(2026, 3, 1), date(2026, 3, 2)).reference == "R00002"

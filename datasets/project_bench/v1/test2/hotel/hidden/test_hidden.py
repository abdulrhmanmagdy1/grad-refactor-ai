from datetime import date
from decimal import Decimal

import pytest

from hotel.invoice import Extra, InvoiceArchive, build_invoice
from hotel.rates import RateTable
from hotel.reports import occupancy_by_type
from hotel.reservations import ReservationBook, Status
from hotel.rooms import Room, RoomCatalog, RoomType

DOUBLE = RoomType("DBL", "Double", Decimal("100.00"), 2)


def make_book() -> tuple[RoomCatalog, ReservationBook]:
    catalog = RoomCatalog()
    catalog.add_type(DOUBLE)
    catalog.add_room(Room("101", DOUBLE, 1))
    catalog.add_room(Room("102", DOUBLE, 1))
    return catalog, ReservationBook(catalog, RateTable())


def test_B1_guest_can_arrive_on_the_day_another_leaves():
    _, book = make_book()
    book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 4))
    assert book.is_available("101", date(2026, 3, 4), date(2026, 3, 6))
    assert book.is_available("101", date(2026, 2, 26), date(2026, 3, 1))
    later = book.reserve("Bob", "101", date(2026, 3, 4), date(2026, 3, 6))
    assert later.room_number == "101"


def test_B2_special_requests_are_not_shared_between_reservations():
    _, book = make_book()
    first = book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 2))
    second = book.reserve("Bob", "102", date(2026, 3, 1), date(2026, 3, 2))
    book.add_request(first.reference, "late arrival")
    assert list(first.special_requests) == ["late arrival"]
    assert list(second.special_requests) == []
    _, other_book = make_book()
    third = other_book.reserve("Cy", "101", date(2026, 3, 1), date(2026, 3, 2))
    assert list(third.special_requests) == []


def test_B3_vat_is_charged_on_extras_too():
    _, book = make_book()
    stay = book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 4))
    invoice = build_invoice(stay, [Extra("Minibar", Decimal("50.00"))])
    assert invoice.subtotal == Decimal("350.00")
    assert invoice.vat == Decimal("49.00")
    assert invoice.total == Decimal("399.00")


def test_S1_archive_does_not_read_files_outside_it(tmp_path):
    (tmp_path / "secret.txt").write_text("database password", encoding="utf-8")
    archive = InvoiceArchive(tmp_path / "invoices")
    try:
        text = archive.read("../secret.txt")
    except (ValueError, PermissionError, LookupError, OSError):
        return
    assert "database password" not in text


def test_keep_archive_reads_its_own_invoices(tmp_path):
    _, book = make_book()
    stay = book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 2))
    archive = InvoiceArchive(tmp_path / "invoices")
    archive.store(build_invoice(stay))
    assert "Guest: Ada" in archive.read("INV-R00001.txt")


def test_keep_overlapping_stays_are_refused():
    _, book = make_book()
    book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 4))
    assert not book.is_available("101", date(2026, 3, 3), date(2026, 3, 5))
    assert not book.is_available("101", date(2026, 2, 28), date(2026, 3, 2))
    assert not book.is_available("101", date(2026, 3, 2), date(2026, 3, 3))
    with pytest.raises(ValueError):
        book.reserve("Bob", "101", date(2026, 2, 27), date(2026, 3, 9))


def test_keep_explicit_requests_are_kept():
    _, book = make_book()
    stay = book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 2), special_requests=["cot"])
    assert list(stay.special_requests) == ["cot"]


def test_keep_cancelled_invoice_bills_only_the_fee():
    _, book = make_book()
    stay = book.reserve("Ada", "101", date(2026, 3, 10), date(2026, 3, 14))
    book.cancel(stay.reference, date(2026, 3, 9))
    invoice = build_invoice(stay, [Extra("Minibar", Decimal("50.00"))])
    assert invoice.subtotal == Decimal("200.00")
    assert invoice.vat == Decimal("28.00")
    assert invoice.total == Decimal("228.00")


def test_keep_purge_removes_only_old_cancellations():
    _, book = make_book()
    old_a = book.reserve("Ada", "101", date(2026, 1, 1), date(2026, 1, 3))
    old_b = book.reserve("Bob", "102", date(2026, 1, 1), date(2026, 1, 3))
    kept = book.reserve("Cy", "101", date(2026, 1, 5), date(2026, 1, 6))
    recent = book.reserve("Di", "102", date(2026, 3, 1), date(2026, 3, 3))
    for reservation in (old_a, old_b, recent):
        book.cancel(reservation.reference, date(2025, 12, 1))
    assert book.purge_cancelled(date(2026, 2, 1)) == 2
    assert [r.reference for r in book.all()] == [kept.reference, recent.reference]


def test_keep_restore_passes_errors_on():
    _, book = make_book()
    with pytest.raises(KeyError):
        book.restore([{"reference": "R00009", "guest": "Ada"}])
    assert book.all() == []


def test_keep_occupancy_counts_the_night_of_the_day():
    catalog, book = make_book()
    book.reserve("Ada", "101", date(2026, 3, 1), date(2026, 3, 3))
    stay = book.reserve("Bob", "102", date(2026, 3, 2), date(2026, 3, 3))
    stay.status = Status.CANCELLED
    assert occupancy_by_type(catalog, book, date(2026, 3, 2)) == {"DBL": (1, 2)}
    assert occupancy_by_type(catalog, book, date(2026, 3, 3)) == {"DBL": (0, 2)}

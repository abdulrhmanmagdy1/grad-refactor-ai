from datetime import date, timedelta

import pytest

from library.catalog import Catalog
from library.fines import fine_for
from library.loans import LoanDesk
from library.models import Book, Loan, Member
from library.storage import ExportStore

DAY = date(2026, 3, 2)


def make_desk() -> LoanDesk:
    catalog = Catalog()
    catalog.add(Book("111", "The Hobbit", "J. R. R. Tolkien", copies=2))
    catalog.add(Book("222", "Animal Farm", "George Orwell"))
    desk = LoanDesk(catalog)
    desk.register(Member("m1", "Sara", max_loans=1))
    desk.register(Member("m2", "Omar"))
    return desk


def test_lending_takes_a_copy_and_returns_a_receipt():
    desk = make_desk()
    text = desk.lend("111", "m2", DAY)
    assert "The Hobbit" in text and "2026-03-16" in text
    assert desk.catalog.available["111"] == 1


def test_a_member_cannot_go_over_the_limit():
    desk = make_desk()
    desk.lend("111", "m1", DAY)
    with pytest.raises(PermissionError):
        desk.lend("222", "m1", DAY)


def test_no_copy_left():
    desk = make_desk()
    desk.lend("222", "m2", DAY)
    with pytest.raises(LookupError):
        desk.lend("222", "m2", DAY)


def test_overdue_long_after_the_due_date():
    desk = make_desk()
    desk.lend("111", "m2", DAY)
    assert desk.is_overdue("L0001", DAY + timedelta(days=30))
    assert not desk.is_overdue("L0001", DAY + timedelta(days=3))


def test_fines_are_capped():
    loan = Loan("L1", "111", "m2", DAY, DAY + timedelta(days=14))
    assert fine_for(loan, DAY + timedelta(days=200)) == 10.0


def test_search_finds_by_author():
    desk = make_desk()
    assert [book.isbn for book in desk.catalog.search("tolkien")] == ["111"]


def test_export_round_trip(tmp_path):
    desk = make_desk()
    store = ExportStore(tmp_path / "exports")
    store.save(desk.catalog, "weekly")
    loaded = store.load("weekly")
    assert sorted(loaded.books) == ["111", "222"]

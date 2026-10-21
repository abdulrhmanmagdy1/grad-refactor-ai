from datetime import date, timedelta

from library.catalog import Catalog
from library.fines import days_late, fine_for
from library.loans import LoanDesk
from library.models import Book, Loan, Member
from library.reports import overdue_summary
from library.storage import ExportStore, checksum

DAY = date(2026, 3, 2)


def make_desk() -> LoanDesk:
    catalog = Catalog()
    catalog.add(Book("111", "The Hobbit", "J. R. R. Tolkien", copies=2))
    catalog.add(Book("222", "Animal Farm", "George Orwell"))
    catalog.add(Book("333", "Nineteen Eighty-Four", "George Orwell"))
    desk = LoanDesk(catalog)
    desk.register(Member("m1", "Sara", max_loans=1))
    return desk


def test_B1_a_returned_book_frees_the_loan_slot():
    desk = make_desk()
    desk.lend("111", "m1", DAY)
    desk.give_back("L0001", DAY + timedelta(days=2))
    desk.lend("222", "m1", DAY + timedelta(days=2))
    assert desk.members["m1"].loans == ["L0002"]


def test_B2_not_overdue_on_the_due_date():
    desk = make_desk()
    desk.lend("111", "m1", DAY)
    due = desk.loans["L0001"].due
    assert not desk.is_overdue("L0001", due)
    assert desk.is_overdue("L0001", due + timedelta(days=1))


def test_B3_no_fine_when_returned_on_time():
    loan = Loan("L1", "111", "m1", DAY, DAY + timedelta(days=14), returned=DAY + timedelta(days=14))
    assert days_late(loan, DAY + timedelta(days=40)) == 0
    assert fine_for(loan, DAY + timedelta(days=40)) == 0


def test_B3_days_late_counts_from_the_due_date():
    loan = Loan("L1", "111", "m1", DAY, DAY + timedelta(days=14))
    assert days_late(loan, DAY + timedelta(days=17)) == 3


def test_B4_searches_do_not_share_results():
    desk = make_desk()
    assert [book.isbn for book in desk.catalog.search("tolkien")] == ["111"]
    assert [book.isbn for book in desk.catalog.search("orwell")] == ["222", "333"]


def test_S1_export_names_cannot_leave_the_folder(tmp_path):
    store = ExportStore(tmp_path / "exports")
    try:
        path = store.export_path("../outside")
    except (ValueError, OSError):
        return
    assert path.resolve().is_relative_to((tmp_path / "exports").resolve())


def test_keep_plain_export_names_still_work(tmp_path):
    desk = make_desk()
    store = ExportStore(tmp_path / "exports")
    first = store.save(desk.catalog, "weekly-2026")
    assert first == checksum(store.export_path("weekly-2026").read_bytes())
    assert sorted(store.load("weekly-2026").books) == ["111", "222", "333"]


def test_keep_checksum_is_the_md5_hex_digest():
    assert checksum(b"abc") == "900150983cd24fb0d6963f7d28e17f72"


def test_keep_remove_author_removes_every_title():
    desk = make_desk()
    assert desk.catalog.remove_author("George Orwell") == 2
    assert sorted(desk.catalog.books) == ["111"]
    assert "222" not in desk.catalog.available


def test_keep_overdue_summary_lists_only_late_open_loans():
    on_time = Loan("L1", "111", "m1", DAY, DAY + timedelta(days=14))
    late = Loan("L2", "222", "m1", DAY - timedelta(days=30), DAY - timedelta(days=16))
    closed = Loan("L3", "333", "m1", DAY - timedelta(days=30), DAY - timedelta(days=16), DAY)
    titles = {"111": "The Hobbit", "222": "Animal Farm", "333": "Nineteen Eighty-Four"}
    lines = overdue_summary([on_time, late, closed], DAY, titles)
    assert len(lines) == 1 and lines[0].startswith("L2 Animal Farm")
    assert "16 days late" in lines[0]


def test_keep_overdue_lists_the_oldest_first():
    desk = make_desk()
    desk.members["m1"].max_loans = 3
    desk.lend("111", "m1", DAY)
    desk.lend("222", "m1", DAY - timedelta(days=5))
    assert [loan.loan_id for loan in desk.overdue(DAY + timedelta(days=60))] == ["L0002", "L0001"]


def test_keep_fines_are_capped():
    loan = Loan("L1", "111", "m1", DAY, DAY + timedelta(days=14))
    assert fine_for(loan, DAY + timedelta(days=300)) == 10.0

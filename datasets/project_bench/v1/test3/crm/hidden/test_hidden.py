from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from crm.activities import ActivityLog
from crm.contacts import ContactBook
from crm.importer import CsvImporter
from crm.pipeline import Pipeline

NOW = datetime(2026, 10, 27, 9, 0)


def test_B1_contacts_without_tags_do_not_share_a_list() -> None:
    book = ContactBook()
    first = book.add_contact("Eve Hart", "eve@hart.io")
    second = book.add_contact("Finn Roe", "finn@roe.io")
    book.tag(first.contact_id, "vip")
    assert first.tags == ["vip"]
    assert second.tags == []
    third = ContactBook().add_contact("Gil Ash", "gil@ash.io")
    assert third.tags == []


def test_keep_tags_merge_into_existing_contact() -> None:
    book = ContactBook()
    first = book.add_contact("Hal Oak", "hal@oak.io", tags=["a"])
    book.add_contact("Hal Oak", "hal@oak.io", tags=["b", "a"])
    assert first.tags == ["a", "b"]
    assert len(book.contacts) == 1


def test_B2_email_duplicates_ignore_letter_case() -> None:
    book = ContactBook()
    first = book.add_contact("Ann Lee", "Ann.Lee@Example.com", tags=["x"])
    again = book.add_contact("Ann Lee", " ann.lee@example.COM ", tags=["y"])
    assert again is first
    assert len(book.contacts) == 1
    assert book.find_by_email("ANN.LEE@EXAMPLE.COM") is first


def test_keep_different_addresses_are_different_contacts() -> None:
    book = ContactBook()
    a = book.add_contact("Ann", "ann@example.com", tags=[])
    b = book.add_contact("Ann", "ann2@example.com", tags=[])
    assert a is not b
    assert book.find_by_email(" ann@example.com ") is a
    assert book.find_by_email("nobody@example.com") is None


def test_B3_history_records_from_and_to_stage() -> None:
    pipeline = Pipeline()
    deal = pipeline.open_deal("Website", "CO1", Decimal("1000"), date(2026, 12, 1))
    pipeline.move(deal.deal_id, "qualified", NOW)
    pipeline.move(deal.deal_id, "proposal", NOW + timedelta(days=2))
    changes = pipeline.changes_for(deal.deal_id)
    assert [(c.from_stage, c.to_stage) for c in changes] == [
        ("lead", "qualified"),
        ("qualified", "proposal"),
    ]
    assert pipeline.entered_stage_at(deal.deal_id, "proposal") == NOW + timedelta(days=2)


def test_keep_move_updates_stage() -> None:
    pipeline = Pipeline()
    deal = pipeline.open_deal("Plan", "CO2", Decimal("500"), date(2026, 11, 1))
    assert pipeline.move(deal.deal_id, "negotiation", NOW).stage == "negotiation"
    assert len(pipeline.history) == 1


def test_S1_upload_cannot_leave_the_import_folder(tmp_path: Path) -> None:
    import_dir = tmp_path / "imports"
    importer = CsvImporter(import_dir)
    try:
        saved = importer.save_upload("../outside.csv", b"name,email\n")
    except (ValueError, OSError):
        saved = None
    assert not (tmp_path / "outside.csv").exists()
    if saved is not None:
        assert import_dir.resolve() in saved.resolve().parents


def test_keep_plain_upload_is_saved_in_the_folder(tmp_path: Path) -> None:
    importer = CsvImporter(tmp_path / "imports")
    saved = importer.save_upload("week43.csv", b"name,email\nIvy,ivy@x.io\n")
    assert saved.read_bytes() == b"name,email\nIvy,ivy@x.io\n"
    assert importer.pending() == ["week43.csv"]
    book = ContactBook()
    assert importer.import_contacts(saved, book).created == 1


def test_keep_unreadable_file_raises(tmp_path: Path) -> None:
    importer = CsvImporter(tmp_path / "imports")
    try:
        importer.import_contacts(tmp_path / "imports" / "missing.csv", ContactBook())
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")


def test_keep_reminders_default_to_current_time() -> None:
    log = ActivityLog()
    past = log.schedule("C1", "call", datetime.now() - timedelta(minutes=5))
    log.schedule("C1", "meeting", datetime.now() + timedelta(days=10))
    assert log.due_reminders() == [past]
    assert log.overdue() == [past]

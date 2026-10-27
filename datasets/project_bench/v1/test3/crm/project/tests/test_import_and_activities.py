from datetime import datetime, timedelta
from pathlib import Path

from crm.activities import ActivityLog
from crm.contacts import ContactBook
from crm.importer import CsvImporter

CSV = (
    "name,email,company,phone,tags\n"
    "Ann Lee,ann@lee.dev,Lee Labs,+1 (555) 010-200,vip; newsletter\n"
    ",nobody@x.io,,,\n"
    "Bo Chan,bo-at-chan.io,,,\n"
    "Ann L.,ann@lee.dev,Lee Labs,,partner\n"
)


def test_import_from_upload(tmp_path: Path) -> None:
    importer = CsvImporter(tmp_path / "imports")
    path = importer.save_upload("leads.csv", CSV.encode())
    assert importer.pending() == ["leads.csv"]
    book = ContactBook()
    result = importer.import_contacts(path, book)
    assert (result.created, result.merged, result.companies) == (1, 1, 1)
    assert [line for line, _ in result.skipped] == [3, 4]
    ann = book.find_by_email("ann@lee.dev")
    assert ann is not None
    assert ann.tags == ["vip", "newsletter", "partner"]
    assert ann.phone == "+1555010200"
    assert book.companies[ann.company_id or ""].domain == "lee.dev"


def test_reminders() -> None:
    log = ActivityLog()
    now = datetime(2026, 10, 27, 9, 0)
    late = log.schedule("C1", "call", now - timedelta(hours=2))
    soon = log.schedule("C1", "email", now + timedelta(hours=5))
    log.schedule("C2", "meeting", now + timedelta(days=3))
    done = log.schedule("C2", "call", now + timedelta(hours=1))
    log.complete(done.activity_id)
    assert log.due_reminders(now=now) == [late, soon]
    assert log.overdue(now=now) == [late]
    assert len(log.for_contact("C2")) == 2

from datetime import date, datetime
from decimal import Decimal

from gym.billing import Ledger, bill_plan_fees
from gym.checkins import CheckInDesk
from gym.classes import GymClass, Schedule
from gym.memberships import MembershipBook
from gym.models import Member, Plan
from gym.reports import monthly_report
from gym.trainers import Trainer, TrainerDiary


def test_monthly_report_summarises_the_month() -> None:
    ledger = Ledger()
    book = MembershipBook(ledger)
    book.register(Member("m1", "Sara", "sara@example.com"))
    book.register(Member("m2", "Omar", "omar@example.com"))
    plan = Plan("Y1", "Yearly", Decimal("30.00"), duration_days=365)
    book.sell("m1", plan, date(2026, 3, 1))
    book.sell("m2", plan, date(2026, 3, 1))

    desk = CheckInDesk(book)
    token = desk.issue_token("m1")
    desk.check_in(token, datetime(2026, 3, 3, 7, 0))

    schedule = Schedule()
    schedule.add(GymClass("hiit-1", "HIIT", datetime(2026, 3, 4, 18, 0), 1))
    schedule.get("hiit-1").book("m1")

    diary = TrainerDiary(ledger)
    diary.add_trainer(Trainer("t1", "Karim", Decimal("40.00")))
    session = diary.book("t1", "m2", datetime(2026, 3, 5, 9, 0), 60)
    diary.complete(session.session_id)

    bill_plan_fees(book, ledger, 2026, 3)
    invoices = ledger.close_month(2026, 3)
    report = monthly_report(book, schedule, desk, diary, invoices, 2026, 3)

    assert "Active memberships: 2" in report
    assert "Most visits: Sara (1)" in report
    assert "Places filled: 1/1 (100%)" in report
    assert "Personal training: 1 completed, 0 cancelled" in report
    assert "Revenue: 100.00" in report

"""Text reports for the desk."""

from __future__ import annotations

from datetime import date

from library.fines import fine_for
from library.models import Loan


def receipt(loan: Loan, title: str) -> str:
    """One line for the member: loan id, title and due date."""
    return f"{loan.loan_id}: {title!r} due {loan.due.isoformat()}"


def lateness(loan: Loan, today: date) -> int:
    """Days past the due date, counting to the return date for closed loans."""
    end = loan.returned if loan.returned is not None else today
    return max(0, (end - loan.due).days)


def overdue_summary(loans: list[Loan], today: date, titles: dict[str, str]) -> list[str]:
    """One line per overdue open loan with its fine, skipping loans without a known title."""
    from library.loans import LOAN_DAYS

    lines = []
    for loan in loans:
        if loan.is_open:
            if loan.due < today:
                if loan.isbn in titles:
                    fine = fine_for(loan, today)
                    if fine > 0:
                        lines.append(
                            f"{loan.loan_id} {titles[loan.isbn]}: {fine:.2f} "
                            f"({lateness(loan, today)} days late, loan period {LOAN_DAYS})"
                        )
    return lines

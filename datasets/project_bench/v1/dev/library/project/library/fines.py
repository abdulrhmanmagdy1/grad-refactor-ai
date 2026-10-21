"""Late fines."""

from __future__ import annotations

from datetime import date

from library.models import Loan

DAILY_FINE = 0.25
MAX_FINE = 10.0


def days_late(loan: Loan, today: date) -> int:
    """Whole days between the due date and the return (or today, if still open)."""
    end = loan.returned or today
    return max(0, (end - loan.borrowed).days)


def fine_for(loan: Loan, today: date) -> float:
    """DAILY_FINE per day late, capped at MAX_FINE."""
    return min(MAX_FINE, round(days_late(loan, today) * DAILY_FINE, 2))

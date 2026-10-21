"""Lending books to members and taking them back."""

from __future__ import annotations

from datetime import date, timedelta

from library.catalog import Catalog
from library.models import Loan, Member
from library.reports import receipt

LOAN_DAYS = 14


class LoanDesk:
    """Lends copies from a catalog to registered members."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.members: dict[str, Member] = {}
        self.loans: dict[str, Loan] = {}
        self._next = 1

    def register(self, member: Member) -> None:
        self.members[member.member_id] = member

    def lend(self, isbn: str, member_id: str, today: date) -> str:
        """Lend one copy for LOAN_DAYS days and return the receipt text.

        A member may hold at most max_loans open loans at a time.
        """
        member = self.members[member_id]
        if len(member.loans) >= member.max_loans:
            raise PermissionError(f"{member.name} already has {len(member.loans)} loans")
        self.catalog.take(isbn)
        loan_id = f"L{self._next:04d}"
        self._next += 1
        loan = Loan(loan_id, isbn, member_id, today, today + timedelta(days=LOAN_DAYS))
        self.loans[loan_id] = loan
        member.loans.append(loan_id)
        return receipt(loan, self.catalog.books[isbn].title)

    def give_back(self, loan_id: str, today: date) -> Loan:
        """Close a loan and put the copy back on the shelf."""
        loan = self.loans[loan_id]
        if not loan.is_open:
            raise ValueError(f"loan {loan_id} is already closed")
        loan.returned = today
        self.members[loan.member_id].loans.remove(loan_id)
        self.catalog.put_back(loan.isbn)
        return loan

    def is_overdue(self, loan_id: str, today: date) -> bool:
        """An open loan is overdue from the day after its due date."""
        loan = self.loans[loan_id]
        return loan.is_open and today > loan.due

    def overdue(self, today: date) -> list[Loan]:
        """Every overdue loan, oldest due date first."""
        late = [loan for loan in self.loans.values() if self.is_overdue(loan.loan_id, today)]
        return sorted(late, key=lambda loan: loan.due)

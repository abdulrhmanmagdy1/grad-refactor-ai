"""Records of the library."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Book:
    isbn: str
    title: str
    author: str
    copies: int = 1


@dataclass
class Member:
    member_id: str
    name: str
    max_loans: int = 3
    loans: list[str] = field(default_factory=list)


@dataclass
class Loan:
    loan_id: str
    isbn: str
    member_id: str
    borrowed: date
    due: date
    returned: date | None = None

    @property
    def is_open(self) -> bool:
        return self.returned is None

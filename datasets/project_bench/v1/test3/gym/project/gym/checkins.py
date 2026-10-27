"""Front-desk check-ins: entry tokens and the visit log."""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from datetime import datetime

from gym.memberships import MembershipBook

TOKEN_ALPHABET = string.ascii_uppercase + string.digits
TOKEN_LENGTH = 10


class CheckInError(Exception):
    """Raised when a member cannot be admitted."""


@dataclass(frozen=True)
class Visit:
    """One admission through the turnstile."""

    member_id: str
    at: datetime


class CheckInDesk:
    """Admits members at the turnstile.

    Each member's app shows an entry token issued here. The turnstile only reads
    the token, so whoever presents a valid token is admitted as its member.
    """

    def __init__(self, book: MembershipBook) -> None:
        self.book = book
        self.visits: list[Visit] = []
        self._tokens: dict[str, str] = {}

    def issue_token(self, member_id: str) -> str:
        """Issue a new entry token for the member; earlier tokens stop working."""
        if member_id not in self.book.members:
            raise CheckInError(f"unknown member {member_id}")
        self._tokens = {t: owner for t, owner in self._tokens.items() if owner != member_id}
        token = "".join(random.choices(TOKEN_ALPHABET, k=TOKEN_LENGTH))
        self._tokens[token] = member_id
        return token

    def check_in(self, token: str, at: datetime) -> Visit:
        """Admit the holder of ``token`` at ``at``.

        The membership must cover that day and a member is admitted at most once
        per day.
        """
        member_id = self._tokens.get(token)
        if member_id is None:
            raise CheckInError("token not recognised")
        membership = self.book.memberships.get(member_id)
        if membership is None or not membership.covers(at.date()):
            raise CheckInError(f"{member_id} has no active membership today")
        if any(v.member_id == member_id and v.at.date() == at.date() for v in self.visits):
            raise CheckInError(f"{member_id} already checked in today")
        visit = Visit(member_id, at)
        self.visits.append(visit)
        return visit

    def visits_in_month(self, year: int, month: int) -> list[Visit]:
        """Visits made in the given month, in the order they happened."""
        return [v for v in self.visits if (v.at.year, v.at.month) == (year, month)]

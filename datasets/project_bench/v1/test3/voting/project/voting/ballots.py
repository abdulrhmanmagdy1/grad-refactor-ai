"""Voting tokens and the ballot box.

An eligible member is issued one token per election. The token is the only link
between a member and a ballot: the box stores the ballot without the member's id, so a
ballot cannot be traced back to who cast it.
"""

from __future__ import annotations

import hashlib
import random
import string
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from voting.audit import AuditLog
from voting.voters import MIN_MEMBERSHIP_DAYS, Roll

TOKEN_ALPHABET = string.ascii_uppercase + string.digits
TOKEN_LENGTH = 12


class NotEligible(Exception):
    """Raised when a member who may not vote asks for a token."""


class InvalidBallot(ValueError):
    """Raised when a ballot is rejected; the token can be used again."""


@dataclass(frozen=True)
class Ballot:
    """A cast ballot: candidates in order of preference, most preferred first."""

    ranking: tuple[str, ...]

    def top_choice(self, remaining: Sequence[str]) -> str | None:
        """Return the highest-ranked candidate still in the count, or None if none is."""
        for candidate in self.ranking:
            if candidate in remaining:
                return candidate
        return None


def token_ref(token: str) -> str:
    """Return a short reference to a token that is safe to write in the audit log."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


class BallotBox:
    """Tokens issued and ballots cast in one election."""

    def __init__(
        self, roll: Roll, candidates: Sequence[str], election_day: date, log: AuditLog
    ) -> None:
        if len(set(candidates)) != len(candidates) or not candidates:
            raise ValueError("candidates must be a non-empty list of distinct names")
        self.roll = roll
        self.candidates = tuple(candidates)
        self.election_day = election_day
        self.log = log
        self.ballots: list[Ballot] = []
        self._unused: set[str] = set()
        self._issued_to: set[str] = set()

    def issue_token(self, member_id: str, at: datetime) -> str:
        """Give an eligible member their voting token for this election.

        Raises NotEligible for a member who may not vote and ValueError for a member who
        already has a token.
        """
        member = self.roll.get(member_id)
        if (
            member.suspended
            or not member.dues_paid
            or self.election_day - member.joined < timedelta(days=MIN_MEMBERSHIP_DAYS)
        ):
            raise NotEligible(f"{member_id} may not vote in this election")
        if member_id in self._issued_to:
            raise ValueError(f"{member_id} already has a token")
        token = "".join(random.choices(TOKEN_ALPHABET, k=TOKEN_LENGTH))
        self._issued_to.add(member_id)
        self._unused.add(token)
        self.log.record("token_issued", at, member_id=member_id)
        return token

    def cast(self, token: str, ranking: Sequence[str], at: datetime) -> Ballot:
        """Cast a ranked ballot with a token and return it.

        The ranking must name at least one candidate, only candidates who are standing,
        and each candidate at most once; otherwise InvalidBallot is raised and the token
        stays usable. An unknown or already used token raises PermissionError.
        """
        if token not in self._unused:
            raise PermissionError("unknown or already used token")
        ref = token_ref(token)
        problem = ""
        if not ranking:
            problem = "the ballot ranks nobody"
        elif any(name not in self.candidates for name in ranking):
            problem = "the ballot ranks someone who is not standing"
        if problem:
            self.log.record("ballot_rejected", at, token_ref=ref, reason=problem)
            raise InvalidBallot(problem)
        self._unused.discard(token)
        ballot = Ballot(tuple(ranking))
        self.ballots.append(ballot)
        self.log.record("ballot_cast", at, token_ref=ref)
        return ballot

    @property
    def turnout(self) -> int:
        """The number of ballots cast so far."""
        return len(self.ballots)

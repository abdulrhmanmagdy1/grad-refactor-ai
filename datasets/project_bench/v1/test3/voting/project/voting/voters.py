"""The membership roll and who may vote."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

MIN_MEMBERSHIP_DAYS = 90


@dataclass
class Member:
    """A club member as kept on the roll."""

    member_id: str
    name: str
    joined: date
    dues_paid: bool = True
    suspended: bool = False


class Roll:
    """All members of the club, by id.

    A member may vote in an election when their dues are paid, they are not suspended,
    and they joined at least ``MIN_MEMBERSHIP_DAYS`` days before election day.
    """

    def __init__(self) -> None:
        self._members: dict[str, Member] = {}

    def add(self, member: Member) -> None:
        """Put a member on the roll; raises ValueError if the id is taken."""
        if member.member_id in self._members:
            raise ValueError(f"member {member.member_id} is already on the roll")
        self._members[member.member_id] = member

    def get(self, member_id: str) -> Member:
        """Return the member; raises KeyError for an unknown id."""
        return self._members[member_id]

    def __len__(self) -> int:
        return len(self._members)

    def is_eligible(self, member_id: str, election_day: date) -> bool:
        """Return True when the member may vote on ``election_day``."""
        member = self._members.get(member_id)
        if member is None or member.suspended or not member.dues_paid:
            return False
        return (election_day - member.joined).days >= MIN_MEMBERSHIP_DAYS

    def eligible_members(self, election_day: date) -> list[Member]:
        """Return the members who may vote on ``election_day``, ordered by id."""
        ids = sorted(self._members)
        return [self._members[i] for i in ids if self.is_eligible(i, election_day)]

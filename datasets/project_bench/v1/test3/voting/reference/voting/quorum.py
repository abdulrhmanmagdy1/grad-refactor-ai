"""Quorum rules: how many ballots make an election valid."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

QUORUM_SHARE = Fraction(1, 3)


@dataclass(frozen=True)
class QuorumReport:
    """Whether an election reached its quorum, with the numbers behind it."""

    eligible: int
    required: int
    cast: int

    @property
    def met(self) -> bool:
        """True when at least the required number of ballots was cast."""
        return self.cast >= self.required

    @property
    def turnout_percent(self) -> float:
        """Ballots cast as a percentage of eligible members, to one decimal place."""
        if self.eligible == 0:
            return 0.0
        return round(100 * self.cast / self.eligible, 1)


def quorum_required(eligible: int, share: Fraction = QUORUM_SHARE) -> int:
    """Return the number of ballots needed for a valid election.

    The quorum is ``share`` of the eligible members, rounded up to a whole ballot, and
    never less than one ballot. Raises ValueError for a negative member count or a share
    outside (0, 1].
    """
    if eligible < 0:
        raise ValueError("eligible must not be negative")
    if not 0 < share <= 1:
        raise ValueError("share must be in (0, 1]")
    needed = eligible * share
    whole = needed.numerator // needed.denominator
    if whole < needed:
        whole += 1
    return max(1, whole)


def check_quorum(eligible: int, cast: int, share: Fraction = QUORUM_SHARE) -> QuorumReport:
    """Return the quorum report for an election with ``cast`` ballots."""
    return QuorumReport(eligible, quorum_required(eligible, share), cast)

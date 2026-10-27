"""Instant-runoff counting of ranked ballots."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from voting.ballots import Ballot


@dataclass
class RunoffResult:
    """The outcome of a count.

    ``rounds`` holds each round's votes for the candidates still in the count,
    ``eliminated`` the candidates knocked out in order, and ``exhausted`` the number of
    ballots that no longer counted for anyone in the final round.
    """

    winner: str | None
    rounds: list[dict[str, int]] = field(default_factory=list)
    eliminated: list[str] = field(default_factory=list)
    exhausted: int = 0


def instant_runoff(ballots: Sequence[Ballot], candidates: Sequence[str]) -> RunoffResult:
    """Count ranked ballots by instant runoff.

    In every round each ballot counts once, for its highest-ranked candidate still in
    the count; a ballot with no such candidate is exhausted and not counted. A candidate
    with more than half of the ballots counted in that round wins. Otherwise the
    candidate with the fewest votes is eliminated (on a tie, the one listed last in
    ``candidates``) and the next round is counted afresh from the ballots. The last
    candidate left wins; when no ballot counts for anyone there is no winner.
    """
    if not candidates:
        raise ValueError("there must be at least one candidate")
    result = RunoffResult(winner=None)
    remaining = list(candidates)
    while True:
        tally = {candidate: 0 for candidate in remaining}
        counted = 0
        for ballot in ballots:
            choice = ballot.top_choice(remaining)
            if choice is not None:
                tally[choice] += 1
                counted += 1
        result.rounds.append({candidate: tally[candidate] for candidate in remaining})
        result.exhausted = len(ballots) - counted
        if counted == 0:
            return result
        leader = max(remaining, key=lambda candidate: tally[candidate])
        if 2 * tally[leader] > counted or len(remaining) == 1:
            result.winner = leader
            return result
        loser = min(reversed(remaining), key=lambda candidate: tally[candidate])
        remaining.remove(loser)
        result.eliminated.append(loser)


def first_preferences(ballots: Sequence[Ballot], candidates: Sequence[str]) -> dict[str, int]:
    """Return how many ballots rank each candidate first."""
    counts = {candidate: 0 for candidate in candidates}
    for ballot in ballots:
        if ballot.ranking and ballot.ranking[0] in counts:
            counts[ballot.ranking[0]] += 1
    return counts

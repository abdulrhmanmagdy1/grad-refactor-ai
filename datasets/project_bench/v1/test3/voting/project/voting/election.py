"""Closing an election: quorum check, count, audit entry and export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from voting.ballots import BallotBox
from voting.counting import RunoffResult, instant_runoff
from voting.export import export_results
from voting.quorum import QuorumReport, check_quorum


@dataclass(frozen=True)
class Outcome:
    """What closing an election produced."""

    quorum: QuorumReport
    result: RunoffResult | None
    exported_to: Path

    @property
    def winner(self) -> str | None:
        """The elected candidate, or None when there was no quorum or no winner."""
        return self.result.winner if self.result else None


def close_election(box: BallotBox, name: str, results_dir: Path, at: datetime) -> Outcome:
    """Close the ballot box, count it if the quorum was met, and export the result.

    Eligibility for the quorum is judged on the box's election day. The count, or the
    missed quorum, is written to the audit log before the files are exported.
    """
    eligible = len(box.roll.eligible_members(box.election_day))
    quorum = check_quorum(eligible, box.turnout)
    result: RunoffResult | None = None
    if quorum.met:
        result = instant_runoff(box.ballots, box.candidates)
        box.log.record("counted", at, winner=result.winner or "", rounds=str(len(result.rounds)))
    else:
        box.log.record("no_quorum", at, cast=str(quorum.cast), required=str(quorum.required))
    path = export_results(results_dir, name, quorum, result)
    return Outcome(quorum, result, path)

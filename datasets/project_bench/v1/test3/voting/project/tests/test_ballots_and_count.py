import json
from datetime import date, datetime

import pytest

from voting.audit import AuditLog, suspicious_activity
from voting.ballots import Ballot, BallotBox, InvalidBallot, NotEligible
from voting.counting import first_preferences, instant_runoff
from voting.election import close_election
from voting.voters import Member, Roll

ELECTION_DAY = date(2026, 6, 1)
AT = datetime(2026, 6, 1, 10, 0)
CANDIDATES = ["Amal", "Basim", "Celia"]


def make_box(members: int = 6) -> BallotBox:
    roll = Roll()
    for n in range(1, members + 1):
        roll.add(Member(f"M{n:02d}", f"Member {n}", date(2020, 1, 1)))
    roll.add(Member("NEW", "Newcomer", date(2026, 5, 1)))
    return BallotBox(roll, CANDIDATES, ELECTION_DAY, AuditLog())


def test_tokens_only_for_eligible_members_and_only_once():
    box = make_box()
    token = box.issue_token("M01", AT)
    assert len(token) == 12
    with pytest.raises(ValueError):
        box.issue_token("M01", AT)
    with pytest.raises(NotEligible):
        box.issue_token("NEW", AT)


def test_cast_and_reuse_of_token():
    box = make_box()
    token = box.issue_token("M01", AT)
    ballot = box.cast(token, ["Basim", "Amal"], AT)
    assert ballot.ranking == ("Basim", "Amal")
    with pytest.raises(PermissionError):
        box.cast(token, ["Amal"], AT)
    assert box.turnout == 1


def test_rejected_ballot_keeps_token_usable():
    box = make_box()
    token = box.issue_token("M02", AT)
    with pytest.raises(InvalidBallot):
        box.cast(token, ["Zed"], AT)
    with pytest.raises(InvalidBallot):
        box.cast(token, [], AT)
    box.cast(token, ["Celia"], AT)
    assert box.turnout == 1


def test_audit_log_chain_and_secrecy():
    box = make_box()
    token = box.issue_token("M03", AT)
    box.cast(token, ["Amal", "Celia"], AT)
    assert box.log.verify()
    assert "Amal" not in json.dumps([e.detail for e in box.log.entries])
    assert suspicious_activity(box.log.entries, max_rejections=3) == []


def test_first_round_majority_wins():
    ballots = [Ballot(("Amal",))] * 4 + [Ballot(("Basim", "Amal"))] * 2 + [Ballot(("Celia",))]
    result = instant_runoff(ballots, CANDIDATES)
    assert result.winner == "Amal"
    assert result.rounds == [{"Amal": 4, "Basim": 2, "Celia": 1}]
    assert result.eliminated == []


def test_no_ballots_no_winner():
    result = instant_runoff([], CANDIDATES)
    assert result.winner is None
    assert result.exhausted == 0


def test_first_preferences():
    ballots = [Ballot(("Celia", "Amal")), Ballot(("Celia",)), Ballot(("Amal",))]
    assert first_preferences(ballots, CANDIDATES) == {"Amal": 1, "Basim": 0, "Celia": 2}


def test_close_election_exports_results(tmp_path):
    box = make_box(members=6)
    for member, ranking in [("M01", ["Amal"]), ("M02", ["Amal", "Basim"]), ("M03", ["Basim"])]:
        box.cast(box.issue_token(member, AT), ranking, AT)
    outcome = close_election(box, "Board 2026", tmp_path / "results", AT)
    assert outcome.quorum.required == 2
    assert outcome.winner == "Amal"
    data = json.loads(outcome.exported_to.read_text(encoding="utf-8"))
    assert data["winner"] == "Amal"
    assert outcome.exported_to.name == "board-2026.json"
    rows = (tmp_path / "results" / "board-2026-rounds.csv").read_text(encoding="utf-8")
    assert rows.splitlines()[1] == "1,Amal,2"
    assert box.log.entries[-1].event == "counted"


def test_close_election_without_quorum(tmp_path):
    box = make_box(members=9)
    box.cast(box.issue_token("M01", AT), ["Celia"], AT)
    outcome = close_election(box, "Board 2026", tmp_path, AT)
    assert not outcome.quorum.met
    assert outcome.winner is None
    assert json.loads(outcome.exported_to.read_text(encoding="utf-8"))["rounds"] == []

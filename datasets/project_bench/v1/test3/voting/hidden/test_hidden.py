import json
import random
from dataclasses import replace
from datetime import date, datetime

import pytest

from voting.audit import AuditLog, suspicious_activity
from voting.ballots import Ballot, BallotBox, InvalidBallot, NotEligible
from voting.counting import instant_runoff
from voting.election import close_election
from voting.export import export_results
from voting.quorum import check_quorum, quorum_required
from voting.voters import Member, Roll

ELECTION_DAY = date(2026, 6, 1)
AT = datetime(2026, 6, 1, 10, 0)
CANDIDATES = ["Amal", "Basim", "Celia"]


def make_box(members: int = 6) -> BallotBox:
    roll = Roll()
    for n in range(1, members + 1):
        roll.add(Member(f"M{n:02d}", f"Member {n}", date(2020, 1, 1)))
    roll.add(Member("EDGE", "Joined 90 days ago", date(2026, 3, 3)))
    roll.add(Member("LATE", "Joined 89 days ago", date(2026, 3, 4)))
    return BallotBox(roll, CANDIDATES, ELECTION_DAY, AuditLog())


def test_B1_quorum_rounds_up_to_a_whole_ballot():
    assert quorum_required(10) == 4
    assert quorum_required(4) == 2
    assert not check_quorum(10, 3).met
    assert check_quorum(10, 4).met


def test_B2_each_round_is_counted_afresh():
    ballots = (
        [Ballot(("Amal",))] * 8
        + [Ballot(("Basim",))] * 5
        + [Ballot(("Celia", "Basim"))] * 4
    )
    result = instant_runoff(ballots, CANDIDATES)
    assert result.rounds == [{"Amal": 8, "Basim": 5, "Celia": 4}, {"Amal": 8, "Basim": 9}]
    assert result.winner == "Basim"
    assert result.eliminated == ["Celia"]


def test_B3_ranking_a_candidate_twice_is_rejected():
    box = make_box()
    token = box.issue_token("M01", AT)
    with pytest.raises(InvalidBallot):
        box.cast(token, ["Amal", "Amal"], AT)
    with pytest.raises(InvalidBallot):
        box.cast(token, ["Basim", "Celia", "Basim"], AT)
    assert box.turnout == 0
    box.cast(token, ["Basim", "Celia"], AT)
    assert box.turnout == 1


def test_S1_tokens_do_not_follow_the_random_seed():
    random.seed(2026)
    first = make_box().issue_token("M01", AT)
    random.seed(2026)
    second = make_box().issue_token("M01", AT)
    assert first != second


def test_keep_tokens_look_the_same():
    token = make_box().issue_token("M02", AT)
    assert len(token) == 12
    assert token.isalnum()


def test_keep_exactly_half_is_not_a_majority():
    ballots = [Ballot(("Amal",))] * 5 + [Ballot(("Basim",))] * 5
    result = instant_runoff(ballots, ["Amal", "Basim"])
    assert result.rounds[0] == {"Amal": 5, "Basim": 5}
    assert result.eliminated == ["Basim"]
    assert result.winner == "Amal"


def test_keep_tie_for_last_and_exhausted_ballots():
    ballots = [Ballot(("Amal",))] * 3 + [Ballot(("Basim",))] * 2 + [Ballot(("Celia",))] * 2
    result = instant_runoff(ballots, CANDIDATES)
    assert result.eliminated == ["Celia"]
    assert result.winner == "Amal"
    assert result.exhausted == 2


def test_keep_box_eligibility_matches_the_roll():
    box = make_box()
    box.issue_token("EDGE", AT)
    with pytest.raises(NotEligible):
        box.issue_token("LATE", AT)


def test_keep_unknown_candidate_and_empty_ballot_rejected():
    box = make_box()
    token = box.issue_token("M03", AT)
    with pytest.raises(InvalidBallot):
        box.cast(token, ["Amal", "Zed"], AT)
    with pytest.raises(InvalidBallot):
        box.cast(token, [], AT)


def test_keep_export_stays_inside_the_results_folder(tmp_path):
    results = tmp_path / "results"
    path = export_results(results, "../../outside/board", check_quorum(3, 0), None)
    assert path.parent == results
    assert path.name == "outside-board.json"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["results"]


def test_keep_tampering_breaks_the_chain():
    log = AuditLog()
    log.record("token_issued", AT, member_id="M01")
    log.record("ballot_cast", AT, token_ref="abc")
    assert log.verify()
    log.entries[0] = replace(log.entries[0], detail={"member_id": "M02"})
    assert not log.verify()


def test_keep_suspicious_activity_reports_each_problem_once():
    log = AuditLog()
    log.record("token_issued", AT, member_id="M01")
    log.record("token_issued", AT, member_id="M01")
    log.record("ballot_cast", AT, token_ref="t1")
    log.record("ballot_cast", AT, token_ref="t1")
    for _ in range(4):
        log.record("ballot_rejected", AT, token_ref="t2", reason="x")
    warnings = suspicious_activity(log.entries, max_rejections=2)
    assert warnings == [
        "#2: M01 was issued a second token",
        "#4: token t1 voted twice",
        "#7: token t2 rejected 3 times",
    ]


def test_keep_close_election_counts_with_quorum(tmp_path):
    box = make_box(members=4)
    for member, ranking in [("M01", ["Celia"]), ("M02", ["Celia", "Amal"])]:
        box.cast(box.issue_token(member, AT), ranking, AT)
    outcome = close_election(box, "Spring vote", tmp_path, AT)
    assert outcome.quorum.eligible == 5
    assert outcome.winner == "Celia"
    data = json.loads(outcome.exported_to.read_text(encoding="utf-8"))
    assert data["quorum"]["met"] is True

from datetime import date
from fractions import Fraction

import pytest

from voting.quorum import check_quorum, quorum_required
from voting.voters import Member, Roll

ELECTION_DAY = date(2026, 6, 1)


def make_roll() -> Roll:
    roll = Roll()
    roll.add(Member("M01", "Aisha", date(2020, 1, 1)))
    roll.add(Member("M02", "Badr", date(2026, 3, 3)))  # exactly 90 days
    roll.add(Member("M03", "Dana", date(2026, 3, 4)))  # 89 days
    roll.add(Member("M04", "Fahad", date(2021, 1, 1), dues_paid=False))
    roll.add(Member("M05", "Ghada", date(2021, 1, 1), suspended=True))
    return roll


def test_eligibility_rules():
    roll = make_roll()
    assert roll.is_eligible("M01", ELECTION_DAY)
    assert roll.is_eligible("M02", ELECTION_DAY)
    assert not roll.is_eligible("M03", ELECTION_DAY)
    assert not roll.is_eligible("M04", ELECTION_DAY)
    assert not roll.is_eligible("M05", ELECTION_DAY)
    assert not roll.is_eligible("NOPE", ELECTION_DAY)


def test_eligible_members_sorted_by_id():
    roll = make_roll()
    assert [m.member_id for m in roll.eligible_members(ELECTION_DAY)] == ["M01", "M02"]


def test_duplicate_member_rejected():
    roll = make_roll()
    with pytest.raises(ValueError):
        roll.add(Member("M01", "Someone", date(2020, 1, 1)))


def test_quorum_is_a_third_of_eligible_members():
    assert quorum_required(9) == 3
    assert quorum_required(30) == 10


def test_quorum_is_at_least_one_ballot():
    assert quorum_required(0) == 1


def test_quorum_with_another_share():
    assert quorum_required(20, Fraction(1, 2)) == 10


def test_bad_share_rejected():
    with pytest.raises(ValueError):
        quorum_required(10, Fraction(3, 2))


def test_quorum_report():
    report = check_quorum(12, 5)
    assert report.required == 4
    assert report.met
    assert report.turnout_percent == 41.7
    assert not check_quorum(12, 3).met

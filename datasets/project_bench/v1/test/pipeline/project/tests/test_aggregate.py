import pytest

from pipeline.aggregate import GroupSummary, shares, summarize, top_groups

ROWS = [
    {"region": "North", "amount": 10.0},
    {"region": "South", "amount": 4.0},
    {"region": "North", "amount": 0.1},
    {"region": "North", "amount": 0.2},
    {"region": "South", "amount": 6.0},
]


def test_summarize():
    north, south = summarize(ROWS, "region", "amount")
    assert north == GroupSummary("North", 3, 10.3, pytest.approx(10.3 / 3), 0.1, 10.0)
    assert south == GroupSummary("South", 2, 10.0, 5.0, 4.0, 6.0)


def test_summarize_nothing():
    assert summarize([], "region", "amount") == []


def test_top_groups():
    summaries = summarize(ROWS, "region", "amount")
    assert [s.key for s in top_groups(summaries, 1)] == ["North"]
    assert [s.key for s in top_groups(summaries, 5, by="count")] == ["North", "South"]
    assert top_groups(summaries, -1) == []
    with pytest.raises(ValueError):
        top_groups(summaries, 1, by="key")


def test_shares():
    summaries = summarize(ROWS, "region", "amount")
    result = shares(summaries)
    assert result["North"] == pytest.approx(100 * 10.3 / 20.3)
    assert sum(result.values()) == pytest.approx(100.0)
    assert shares([GroupSummary("A", 1, 0.0, 0.0, 0.0, 0.0)]) == {"A": 0.0}

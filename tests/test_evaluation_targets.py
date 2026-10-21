"""Numerical targets: exact binomial limits, derivation rule and assessment."""

import csv
import importlib.util
import math
from pathlib import Path

import pytest

from refactor_ai.evaluation import report, targets

_spec = importlib.util.spec_from_file_location(
    "evaluation_report_helpers", Path(__file__).with_name("test_evaluation_report.py")
)
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
make = _helpers.make  # one EvaluationRecord-validated record


def test_clopper_pearson_matches_known_values():
    lower, upper = targets.clopper_pearson(5, 20)
    assert (round(lower, 4), round(upper, 4)) == (0.0866, 0.4910)  # textbook example
    assert targets.clopper_pearson(0, 84) == (0.0, pytest.approx(1 - 0.025 ** (1 / 84)))
    assert targets.clopper_pearson(84, 84) == (pytest.approx(0.025 ** (1 / 84)), 1.0)
    for successes in (1, 6, 46, 69, 83):
        low, high = targets.clopper_pearson(successes, 84)
        mirror_low, mirror_high = targets.clopper_pearson(84 - successes, 84)
        assert low == pytest.approx(1 - mirror_high, abs=1e-12)
        assert high == pytest.approx(1 - mirror_low, abs=1e-12)
        assert low < successes / 84 < high
        # The limits are where the exact binomial tails equal 2.5 %.
        assert 1 - targets.binomial_cdf(successes - 1, 84, low) == pytest.approx(0.025)
        assert targets.binomial_cdf(successes, 84, high) == pytest.approx(0.025)
    assert targets.binomial_cdf(5, 10, 0.5) == pytest.approx(638 / 1024)
    with pytest.raises(ValueError):
        targets.clopper_pearson(5, 4)


def test_targets_use_the_least_favourable_attainable_count():
    derived = targets.derive_arm_targets(
        {"B": {"proposal_ready": [1, 4], "syntax_valid": [81, 84], "failed": [0, 3]}},
        n=84,
        test_n=88,
    )["B"]
    assert derived["proposal_ready"]["count_used"] == 1
    assert derived["syntax_valid"]["count_used"] == 81
    assert derived["failed"]["count_used"] == 3
    floor = derived["syntax_valid"]
    assert floor["limit_rate"] <= targets.clopper_pearson(81, 84)[0]
    needed = floor["test_count_needed"]
    assert needed / 88 >= floor["limit_rate"] > (needed - 1) / 88
    ceiling = derived["failed"]
    assert ceiling["limit_rate"] >= targets.clopper_pearson(3, 84)[1]
    allowed = ceiling["test_count_allowed"]
    assert allowed / 88 <= ceiling["limit_rate"] < (allowed + 1) / 88


def test_direction_needs_a_significant_difference():
    assert targets.direction(65, 2, 1e-16) == "first"
    assert targets.direction(2, 25, 1e-5) == "second"
    assert targets.direction(2, 5, 0.45) == "none"
    assert targets.direction(3, 3, 0.0) == "none"


def frozen_targets(limit: float) -> dict:
    floor = {"kind": "floor", "limit_rate": limit}
    return {
        "rule": "test rule",
        "arms": {
            "A": {"proposal_ready": floor, "failed": {"kind": "ceiling", "limit_rate": 0.1}},
            "C": {"proposal_ready": floor},
            "D": {"proposal_ready": floor},
        },
        "directions": [
            {"comparison": "C vs A", "expected": "first"},
            {"comparison": "D vs C", "expected": "first"},
            {"comparison": "D vs B", "expected": "first"},
            {"comparison": "B vs A", "expected": "none"},
        ],
    }


def test_assessment_marks_targets_and_directions():
    rows = []
    for i in range(20):
        rows.append(
            make(f"c{i}", "A", ready=i < 2, failure="provider_timeout" if i == 19 else "none")
        )
        rows.append(make(f"c{i}", "C", ready=i < 18))
        rows.append(make(f"c{i}", "D", ready=i < 9))
    metrics = report.arm_metrics(rows)
    paired = report.paired_comparisons(rows)
    result = targets.assess(frozen_targets(0.4), metrics, paired)
    met = {(row["arm"], row["metric"]): row["met"] for row in result["arms"]}
    assert met == {
        ("A", "proposal_ready"): False,  # 2/20 < 0.4
        ("A", "failed"): True,  # 1/20 <= 0.1
        ("C", "proposal_ready"): True,
        ("D", "proposal_ready"): True,  # 9/20 >= 0.4
    }
    outcomes = {item["comparison"]: item["outcome"] for item in result["comparisons"]}
    assert outcomes == {
        "C vs A": "confirmed",  # 16 C-only cases against 0
        "D vs C": "reversed",  # C accepts 9 more cases
        "D vs B": "not measured",  # arm B was not run
        "B vs A": "not measured",
    }


def test_report_assesses_a_freeze_record(tmp_path):
    rows = [make(f"c{i}", arm, ready=i < 3) for i in range(5) for arm in "AC"]
    freeze = {"protocol_version": "eval-v1", "frozen_on": "2026-10-21"}
    freeze["targets"] = frozen_targets(0.5)
    written = report.build_report(rows, tmp_path, freeze=freeze)
    assert {"targets.csv", "target_directions.csv"} <= set(written)
    with open(written["targets.csv"], encoding="utf-8", newline="") as handle:
        table = list(csv.DictReader(handle))
    assert [(row["arm"], row["metric"], row["met"]) for row in table] == [
        ("A", "proposal_ready", "True"),
        ("A", "failed", "True"),
        ("C", "proposal_ready", "True"),
        ("D", "proposal_ready", ""),  # not run: no assessment
    ]
    summary = open(written["summary.md"], encoding="utf-8").read()
    assert "## Pre-registered targets" in summary and "| D | proposal_ready |" in summary
    assert "not run" in summary
    with pytest.raises(report.ReportError, match="no numerical targets"):
        report.build_report(rows, tmp_path, freeze={"protocol_version": "eval-v1"})
    # Without a freeze record nothing about targets is written.
    plain = report.build_report(rows, tmp_path / "plain")
    assert "targets.csv" not in plain
    assert "Pre-registered" not in open(plain["summary.md"], encoding="utf-8").read()
    assert math.isclose(float(table[0]["limit_rate"]), 0.5)

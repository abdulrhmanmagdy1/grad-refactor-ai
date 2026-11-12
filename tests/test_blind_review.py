"""Tests for the blind human-review toolkit (prepare + aggregate scripts)."""

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


prepare = _load_script("prepare_blind_review")
aggregate_script = _load_script("aggregate_blind_review")


def _row(case_id: str, group: str, code: str, status: str = "executed") -> dict:
    return {
        "case_id": case_id,
        "group": group,
        "status": status,
        "refactoring_type": "long-function",
        "model": "mock-transform",
        "original_code": f"def {case_id.replace('-', '_')}():\n    return 1\n",
        "refactored_code": code,
    }


def _records() -> dict[str, list[dict]]:
    return {
        "case-a": [
            _row("case-a", "Group-A-Baseline", "def a():\n    x = 1\n    return x\n"),
            _row(
                "case-a",
                "Group-B-MultiAgent",
                "def a_helper():\n    return 1\n\ndef a():\n    return a_helper()\n",
            ),
        ],
        "case-b": [
            _row("case-b", "Group-A-Baseline", "def b():\n    return 1\n"),
            _row("case-b", "Group-B-MultiAgent", "def b():\n    value = 1\n    return value\n"),
        ],
        "case-c-single": [
            _row("case-c-single", "Group-A-Baseline", "def c():\n    return 1\n"),
        ],
    }


def test_packet_blinds_group_names_and_labels_candidates():
    packet, key_rows, sheet_rows = prepare.build_review(_records())

    assert "Group-A-Baseline" not in packet
    assert "Group-B-MultiAgent" not in packet
    assert "Candidate 1" in packet and "Candidate 2" in packet
    # Single-candidate cases are excluded from the blind comparison.
    assert "case-c-single" not in packet

    key_by_case: dict[str, set[str]] = {}
    for row in key_rows:
        key_by_case.setdefault(row["case_id"], set()).add(row["group"])
    assert key_by_case == {
        "case-a": {"Group-A-Baseline", "Group-B-MultiAgent"},
        "case-b": {"Group-A-Baseline", "Group-B-MultiAgent"},
    }
    # Every candidate code shown in the packet appears under exactly one label.
    assert len(sheet_rows) == 2 * 2 * 5


def test_build_is_deterministic_for_a_seed():
    stamp = "2026-11-08T00:00:00Z"
    first = prepare.build_review(_records(), seed="s1", generated_at=stamp)
    second = prepare.build_review(_records(), seed="s1", generated_at=stamp)
    assert first == second
    different = prepare.build_review(_records(), seed="s2", generated_at=stamp)

    # The key still maps the same groups; only the anonymised order may differ.
    def membership(rows: list[dict]) -> list[tuple[str, str]]:
        return sorted((row["case_id"], row["group"]) for row in rows)

    assert membership(different[1]) == membership(first[1])


def test_sheet_rows_are_prefilled_blank():
    _, _, sheet_rows = prepare.build_review(_records(), raters_per_candidate=3)
    assert len(sheet_rows) == 2 * 2 * 3
    for row in sheet_rows:
        assert row["rater"] == ""
        assert row["comment"] == ""
        for dimension in prepare.DIMENSIONS:
            assert row[dimension] == ""


def test_write_outputs_refuses_to_clobber_and_force_overrides(tmp_path):
    packet, key_rows, sheet_rows = prepare.build_review(_records())
    prepare.write_outputs(tmp_path, packet, key_rows, sheet_rows)

    sheet = tmp_path / "score_sheet.csv"
    with open(sheet, "a", encoding="utf-8") as handle:
        handle.write("case-a,Candidate 1,reviewer,5,5,5,looks good\n")

    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        prepare.write_outputs(tmp_path, packet, key_rows, sheet_rows)

    prepare.write_outputs(tmp_path, packet, key_rows, sheet_rows, force=True)
    assert "reviewer" not in sheet.read_text(encoding="utf-8")


def test_load_executed_records_ignores_unavailable_and_codeless_rows(tmp_path):
    csv_path = tmp_path / "results.csv"
    columns = [
        "case_id",
        "group",
        "status",
        "refactoring_type",
        "model",
        "original_code",
        "refactored_code",
    ]
    rows = [
        _row("case-x", "Group-A-Baseline", "def x():\n    return 1\n"),
        _row("case-x", "Group-B-MultiAgent", "", status="executed"),
        _row("case-x", "Group-C-FineTunedSingle", "", status="provider_unavailable"),
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    loaded = prepare.load_executed_records(csv_path)
    assert list(loaded) == ["case-x"]
    assert len(loaded["case-x"]) == 1


def _sheet_columns() -> list[str]:
    return ["case_id", "candidate_label", "rater", *aggregate_script.DIMENSIONS, "comment"]


def _key() -> dict[tuple[str, str], str]:
    return {
        ("c1", "Candidate 1"): "Group-A-Baseline",
        ("c1", "Candidate 2"): "Group-B-MultiAgent",
        ("c2", "Candidate 1"): "Group-A-Baseline",
    }


def _rating(
    case_id: str,
    label: str,
    rater: str,
    correctness: int,
    readability: int,
    maintain: int,
) -> dict:
    return {
        "case_id": case_id,
        "candidate_label": label,
        "rater": rater,
        "correctness_1_5": correctness,
        "readability_1_5": readability,
        "maintainability_1_5": maintain,
    }


def test_aggregate_computes_group_means_and_inter_rater_ranges():
    ratings = [
        _rating("c1", "Candidate 1", "r1", 4, 4, 4),
        _rating("c1", "Candidate 1", "r2", 2, 2, 2),
        _rating("c1", "Candidate 2", "r1", 5, 5, 5),
        _rating("c2", "Candidate 1", "r1", 3, 4, 5),
        _rating("c9", "Candidate 1", "r1", 1, 1, 1),  # unknown pair
    ]
    stats = aggregate_script.aggregate(_key(), ratings)

    assert stats["rows_used"] == 4
    assert stats["skipped_unknown_pair"] == 1

    group_a = stats["by_group"]["Group-A-Baseline"]
    assert group_a["n_ratings"] == 3
    assert group_a["correctness_1_5"]["mean"] == 3.0
    assert group_a["readability_1_5"]["mean"] == 3.333
    assert group_a["maintainability_1_5"]["mean"] == 3.667
    assert group_a["overall_mean"] == 3.333

    group_b = stats["by_group"]["Group-B-MultiAgent"]
    assert group_b["n_ratings"] == 1
    assert group_b["overall_mean"] == 5
    assert group_b["correctness_1_5"]["pstdev"] is None  # single rating cannot spread

    inter = stats["inter_rater"]
    assert inter["items_with_multiple_raters"] == 1
    for dimension in aggregate_script.DIMENSIONS:
        assert inter["dimension_ranges"][dimension] == {"items": 1, "mean_range": 2.0}


def test_load_scores_skips_blank_and_invalid_rows(tmp_path):
    sheet = tmp_path / "score_sheet.csv"
    with open(sheet, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_sheet_columns())
        writer.writeheader()
        writer.writerow(
            {"case_id": "c1", "candidate_label": "Candidate 1", "rater": "", "correctness_1_5": ""}
        )
        writer.writerow(
            {
                "case_id": "c1",
                "candidate_label": "Candidate 1",
                "rater": "r1",
                "correctness_1_5": "high",
                "readability_1_5": "4",
                "maintainability_1_5": "4",
            }
        )
        writer.writerow(
            {
                "case_id": "c1",
                "candidate_label": "Candidate 1",
                "rater": "r1",
                "correctness_1_5": "7",
                "readability_1_5": "4",
                "maintainability_1_5": "4",
            }
        )
        writer.writerow(
            {
                "case_id": "c1",
                "candidate_label": "Candidate 1",
                "rater": "r2",
                "correctness_1_5": "4",
                "readability_1_5": "4",
                "maintainability_1_5": "4",
            }
        )

    valid, skipped, rows_total = aggregate_script.load_scores(sheet)
    assert rows_total == 4
    assert len(valid) == 1
    assert valid[0]["rater"] == "r2"
    assert skipped == {"blank_rater": 1, "invalid_scores": 2}


def test_aggregate_cli_stops_when_nothing_was_rated(tmp_path, monkeypatch):
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    (review_dir / "review_key.csv").write_text(
        "case_id,candidate_label,group,model,refactoring_type\n"
        "c1,Candidate 1,Group-A-Baseline,mock,mock\n",
        encoding="utf-8",
    )
    (review_dir / "score_sheet.csv").write_text(
        ",".join(_sheet_columns()) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["aggregate_blind_review.py", "--review-dir", str(review_dir)])
    with pytest.raises(SystemExit, match="No filled ratings"):
        aggregate_script.main()

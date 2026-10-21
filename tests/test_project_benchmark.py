"""The seeded-project benchmark: manifests, validation, matching, fix scoring and metrics."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from refactor_ai.contracts import Disposition
from refactor_ai.project import benchmark
from refactor_ai.project.models import Category, Finding, Fix, FixCheck, Severity
from refactor_ai.project.testrun import ProjectTestRunner

ROOT = Path(__file__).resolve().parents[1]

OPS = '''"""Arithmetic helpers."""


def clamp(value: int, low: int, high: int) -> int:
    """The value limited to low..high, both ends included."""
    if value < low:
        return low
    if value >= high:
        return high - 1
    return value


def total(values: list[int]) -> int:
    """The sum of the values."""
    return sum(values)
'''
FIXED_CLAMP = OPS.replace(
    "if value >= high:\n        return high - 1", "if value > high:\n        return high"
)
VISIBLE = "from calc.ops import clamp\n\n\ndef test_low_end():\n    assert clamp(-3, 0, 5) == 0\n"
HIDDEN = (
    "from calc.ops import clamp, total\n\n\n"
    "def test_B1_the_high_end_is_kept():\n    assert clamp(10, 0, 5) == 5\n\n\n"
    "def test_keep_total():\n    assert total([1, 2]) == 3\n"
)


def manifest(**changes) -> dict:
    data = {
        "schema_version": 1,
        "name": "calc",
        "description": "Arithmetic helpers.",
        "author": "tests",
        "issues": [
            {
                "id": "B1",
                "category": "bug",
                "kind": "off-by-one",
                "file": "calc/ops.py",
                "lines": [8, 9],
                "anchor": "if value >= high:",
                "symbol": "clamp",
                "description": "The upper end is excluded although the docstring includes it.",
                "fixable_in_function": True,
                "hidden_tests": ["test_B1_the_high_end_is_kept"],
            }
        ],
        "decoys": [
            {
                "id": "D1",
                "file": "calc/ops.py",
                "lines": [15, 15],
                "anchor": "return sum(values)",
                "why_it_is_fine": "Summing a list of integers is exactly what is wanted.",
            }
        ],
    }
    data.update(changes)
    return data


def make_project(
    base: Path,
    *,
    data: dict | None = None,
    ops: str = OPS,
    hidden: str = HIDDEN,
    reference: str | None = FIXED_CLAMP,
) -> benchmark.BenchProject:
    root = base / "dev" / "calc"
    if root.exists():
        shutil.rmtree(root)
    (root / "project" / "calc").mkdir(parents=True)
    (root / "project" / "tests").mkdir()
    (root / "hidden").mkdir()
    (root / "project" / "calc" / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    (root / "project" / "calc" / "ops.py").write_text(ops, encoding="utf-8", newline="\n")
    (root / "project" / "tests" / "test_ops.py").write_text(VISIBLE, encoding="utf-8", newline="\n")
    (root / "hidden" / "test_hidden.py").write_text(hidden, encoding="utf-8", newline="\n")
    if reference is not None:
        (root / "reference" / "calc").mkdir(parents=True)
        (root / "reference" / "calc" / "ops.py").write_text(
            reference, encoding="utf-8", newline="\n"
        )
    (root / "manifest.json").write_text(json.dumps(data or manifest()), encoding="utf-8")
    return benchmark.BenchProject.load(root)


def finding(**changes) -> Finding:
    values = {
        "id": "F001",
        "category": Category.BUG,
        "severity": Severity.HIGH,
        "source": "agent:bug_finder",
        "file": "calc/ops.py",
        "line_start": 8,
        "line_end": 8,
        "symbol": "clamp",
        "title": "Upper bound excluded",
        "explanation": "The high end is never returned.",
    }
    values.update(changes)
    return Finding(**values)


def fix(fix_id: str, proposed: str, disposition=Disposition.PROPOSAL_READY) -> Fix:
    original = OPS.split("\n\n\n")[1] + "\n"
    check = FixCheck(status="pass")
    return Fix(
        id=fix_id,
        finding_ids=["F001"],
        file="calc/ops.py",
        symbol="clamp",
        line_start=4,
        line_end=10,
        original=original,
        proposed=proposed,
        produced_by="agent:fixer",
        syntax=check,
        static_recheck=check,
        tests=check,
        review=check,
        disposition=disposition,
    )


# --- manifest ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "issue_changes",
    [
        {"category": "architecture", "modules": []},
        {"hidden_tests": []},
        {"fixable_in_function": False},
        {"symbol": None},
        {"hidden_tests": ["test_B2_wrong_prefix"]},
        {"lines": [9, 8]},
        {"file": "calc\\ops.py"},
        {"kind": "Off By One"},
        {"category": "refactoring"},
    ],
)
def test_invalid_issues_are_rejected(issue_changes):
    data = manifest()
    data["issues"][0].update(issue_changes)
    with pytest.raises(ValidationError):
        benchmark.Manifest.model_validate(data)


def test_ids_are_unique_and_the_folder_names_the_project(tmp_path):
    data = manifest()
    data["decoys"][0]["id"] = "D1"
    data["issues"].append({**data["issues"][0], "hidden_tests": ["test_B1_x"]})
    with pytest.raises(ValidationError, match="unique"):
        benchmark.Manifest.model_validate(data)
    with pytest.raises(ValueError, match="folder name"):
        make_project(tmp_path, data=manifest(name="other"))


def test_projects_zip_like_an_upload_and_hash_stably(tmp_path):
    project = make_project(tmp_path)
    assert project.files() == ["calc/__init__.py", "calc/ops.py", "tests/test_ops.py"]
    assert project.zip_bytes() == project.zip_bytes()
    first = project.sha256()
    ops = project.project_dir / "calc" / "ops.py"
    ops.write_bytes(ops.read_bytes().replace(b"\n", b"\r\n"))
    assert project.sha256() == first  # line endings do not change the hash
    ops.write_text(OPS + "\n", encoding="utf-8")
    assert project.sha256() != first
    assert [p.name for p in benchmark.load_split("dev", tmp_path)] == ["calc"]
    assert benchmark.load_split("test", tmp_path) == []


# --- validation --------------------------------------------------------------------------


def test_a_correct_project_validates(tmp_path):
    result = benchmark.validate(make_project(tmp_path), ProjectTestRunner())
    assert result.ok, result.problems
    assert "tests: 1 visible, 2 hidden" in result.notes


def test_validation_finds_wrong_places_and_references(tmp_path):
    data = manifest()
    data["issues"][0]["anchor"] = "if value > high:"
    data["decoys"][0]["lines"] = [40, 41]
    unrelated = FIXED_CLAMP.replace("return sum(values)", "return sum(values) + 0")
    project = make_project(tmp_path, data=data, reference=unrelated)
    problems = benchmark.validate(project, run_tests=False).problems
    assert any("anchor" in p for p in problems)
    assert any("D1: lines [40, 41] are past the end" in p for p in problems)
    assert any("changes calc/ops.py:total" in p for p in problems)

    data = manifest()
    data["issues"][0]["symbol"] = "total"
    problems = benchmark.validate(
        make_project(tmp_path, data=data, reference=None), run_tests=False
    ).problems
    assert any("not in total" in p for p in problems)
    assert any("does not change calc/ops.py" in p for p in problems)


def test_validation_finds_hidden_test_problems(tmp_path):
    hidden = HIDDEN.replace("def test_keep_total", "def test_total") + (
        "\n\nclass TestGrouped:\n    def test_x(self):\n        pass\n"
    )
    problems = benchmark.validate(make_project(tmp_path, hidden=hidden), run_tests=False).problems
    assert "hidden test test_total is neither listed nor a test_keep_* test" in problems
    assert "there is no test_keep_* test" in problems
    assert "hidden tests must be top-level functions" in problems


def test_validation_runs_the_tests_both_ways(tmp_path):
    # The reference does not fix the bug and the hidden test passes on the seeded code.
    hidden = HIDDEN.replace("clamp(10, 0, 5) == 5", "clamp(3, 0, 5) == 3")
    project = make_project(tmp_path, hidden=hidden, reference=OPS)
    problems = benchmark.validate(project, ProjectTestRunner()).problems
    assert "B1: hidden test test_B1_the_high_end_is_kept does not fail on the project" in problems

    project = make_project(tmp_path, reference=OPS)
    problems = benchmark.validate(project, ProjectTestRunner()).problems
    assert any("fails with the reference fix" in p and "test_B1" in p for p in problems)


def test_static_findings_outside_the_seeded_places_are_problems(tmp_path):
    ops = OPS + "\n\ndef unused(items=[]):\n    return items\n"
    problems = benchmark.validate(make_project(tmp_path, ops=ops), run_tests=False).problems
    assert any("static finding outside every seeded place" in p and "B006" in p for p in problems)


# --- matching ----------------------------------------------------------------------------


def test_findings_match_seeded_places_within_two_lines():
    data = benchmark.Manifest.model_validate(manifest())
    issue = data.issues[0]
    assert benchmark.matches(finding(line_start=6, line_end=6), issue)
    assert benchmark.matches(finding(line_start=11, line_end=12), issue)
    assert not benchmark.matches(finding(line_start=12, line_end=12), issue)
    assert not benchmark.matches(finding(line_start=None, line_end=None), issue)
    assert not benchmark.matches(finding(file="calc/other.py"), issue)

    result = benchmark.match_findings(
        [
            finding(),
            finding(id="F002", category=Category.QUALITY, line_start=15, line_end=15),
            finding(id="F003", line_start=1, line_end=1),
        ],
        data,
    )
    assert result["detected"] == {"B1": ["F001"]} and result["right_category"] == {"B1": True}
    assert result["finding_decoys"] == {"F002": ["D1"], "F003": []}
    assert result["decoys_hit"] == {"D1": ["F002"]}


def test_architecture_issues_match_by_modules_or_file():
    issue = benchmark.Issue(
        id="A1",
        category="architecture",
        kind="import-cycle",
        file="app/a.py",
        lines=[3, 3],
        anchor="import app.b",
        modules=["app.a", "app.b"],
        description="a and b import each other.",
    )
    cycle = finding(
        category=Category.ARCHITECTURE,
        file="app/c.py",
        line_start=None,
        line_end=None,
        symbol="app.a",
        explanation="app.a -> app.b -> app.a",
    )
    assert benchmark.matches(cycle, issue)
    assert not benchmark.matches(cycle.model_copy(update={"explanation": "app.a -> app.bc"}), issue)
    assert not benchmark.matches(cycle.model_copy(update={"category": Category.QUALITY}), issue)
    assert benchmark.matches(cycle.model_copy(update={"file": "app/a.py", "symbol": "x"}), issue)
    assert benchmark._mentions("see app.a.", "app.a")
    assert not benchmark._mentions("app.a.b", "app.a")


# --- fixes -------------------------------------------------------------------------------


def test_fixes_are_scored_alone_and_together(tmp_path):
    project = make_project(tmp_path)
    original = OPS.split("\n\n\n")[1] + "\n"
    good = original.replace(
        "if value >= high:\n        return high - 1", "if value > high:\n        return high"
    )
    harmful = original.replace("return low\n", "return high\n")
    no_effect = original.replace('"""The value', '"""Return the value')
    fixes = [
        fix("X001", good),
        fix("X002", harmful, Disposition.UNCERTAIN),
        fix("X003", no_effect, Disposition.REJECTED),
        fix("X004", None, Disposition.FAILED),
    ]
    scores = benchmark.evaluate_fixes(project, project.project_dir, fixes, ProjectTestRunner())
    outcomes = {entry["fix"]: entry for entry in scores["per_fix"]}
    assert outcomes["X001"]["outcome"] == "resolves" and outcomes["X001"]["resolved"] == ["B1"]
    assert outcomes["X002"]["outcome"] == "harmful"
    assert outcomes["X002"]["broken"] == ["tests.test_ops::test_low_end"]
    assert outcomes["X003"]["outcome"] == "no_effect"
    assert outcomes["X004"]["outcome"] == "no_proposal"
    assert scores["ready_together"] == {"fixes": ["X001"], "resolved": ["B1"], "broken": []}


# --- metrics -----------------------------------------------------------------------------


def record(project: str, detected: list[str], ready: str = "resolves") -> dict:
    return {
        "project": project,
        "review_s": 10.0,
        "calls": [{}, {}],
        "findings": [
            {"id": "F001", "source": "static:ruff:B006"},
            {"id": "F002", "source": "agent:bug_finder"},
            {"id": "F003", "source": "agent:quality_security"},
        ],
        "matching": {
            "detected": {"B1": ["F001"] if "B1" in detected else []},
            "right_category": {"B1": "B1" in detected},
            "finding_issues": {"F001": ["B1"] if "B1" in detected else [], "F002": [], "F003": []},
            "finding_decoys": {"F002": ["D1"], "F003": []},
            "decoys_hit": {"D1": ["F002"]},
        },
        "fix_scores": {
            "per_fix": [
                {"fix": "X001", "disposition": "proposal_ready", "outcome": ready, "resolved": []}
            ],
            "ready_together": {"resolved": ["B1"] if ready == "resolves" else []},
        },
        "dropped": [{"issues": ["B1"]}, {"issues": []}],
    }


def test_arm_summary_and_paired_comparison():
    manifests = {"calc": benchmark.Manifest.model_validate(manifest())}
    summary = benchmark.summarize_arm([record("calc", ["B1"])], manifests)
    assert summary["issues"]["count"] == 1 and summary["issues"]["total"] == 1
    assert summary["issues_by_category"]["bug"]["right_category"] == 1
    assert summary["findings"]["total"] == 3 and summary["findings"]["on_decoy"] == 1
    assert summary["findings"]["by_origin"]["agent:unlabelled"] == 1
    assert summary["decoys_hit"]["count"] == 1
    assert summary["fixable_issues"]["resolved_by_ready_fixes"]["count"] == 1
    assert summary["ready_fixes"] == 1 and summary["ready_harmful"] == []
    assert summary["checker"] == {"dropped": 2, "dropped_on_seeded_issue": 1}
    harmful = benchmark.summarize_arm([record("calc", [], ready="harmful")], manifests)
    assert harmful["ready_harmful"] == ["calc:X001"] and harmful["issues"]["count"] == 0
    paired = benchmark.compare_detection([record("calc", [])], [record("calc", ["B1"])], manifests)
    assert paired == {
        "both": 0,
        "only_first": 0,
        "only_second": 1,
        "neither": 0,
        "mcnemar_p": 1.0,
    }


def test_judged_pairs_are_blind_and_confirm_detection(tmp_path):
    project = make_project(tmp_path)
    located = record("calc", ["B1"])
    located["findings"][0].update(
        {"file": "calc/ops.py", "line_start": 8, "title": "Mutable default", "explanation": "x"}
    )
    other_arm = json.loads(json.dumps(located))
    other_arm["findings"][0]["id"] = "F009"  # ids differ between arms; the pair does not
    other_arm["matching"]["detected"] = {"B1": ["F009"]}
    other_arm["matching"]["finding_issues"] = {"F009": ["B1"]}
    pairs = benchmark.adjudication_pairs([located, other_arm], {"calc": project})
    assert len(pairs) == 1
    [pair] = pairs
    assert "source" not in pair["finding"] and pair["problem"]["code"].startswith("    if value")
    assert pair["finding"]["title"] == "Mutable default" and pair["problem"]["lines"] == [8, 9]

    manifests = {"calc": project.manifest}
    assert benchmark.confirmed(located, {}) == {"B1": None}
    same = {pair["pair"]: {"same": True}}
    different = {pair["pair"]: {"same": False}}
    assert benchmark.confirmed(located, same) == {"B1": True}
    assert benchmark.confirmed(located, different) == {"B1": False}
    assert benchmark.confirmed(record("calc", []), {}) == {"B1": False}
    summary = benchmark.summarize_arm([located], manifests, different)
    assert summary["issues"]["count"] == 1 and summary["confirmed"]["issues"]["count"] == 0
    assert summary["confirmed"]["by_category"]["bug"]["total"] == 1
    unjudged = benchmark.summarize_arm([located], manifests, {})
    assert unjudged["confirmed"]["issues_located_but_not_judged"] == 1
    assert benchmark.summarize_arm([located], manifests)["confirmed"] is None
    paired = benchmark.compare_detection([located], [other_arm], manifests, different)
    assert paired["neither"] == 1
    assert benchmark.compare_detection([located], [other_arm], manifests, same)["both"] == 1


def test_wilson_and_mcnemar():
    assert benchmark.wilson(0, 0) is None
    low, high = benchmark.wilson(8, 10)
    assert low == pytest.approx(0.4902, abs=1e-4) and high == pytest.approx(0.9433, abs=1e-4)
    assert benchmark.mcnemar_exact(0, 0) == 1.0
    assert benchmark.mcnemar_exact(0, 6) == pytest.approx(0.03125)
    assert benchmark.mcnemar_exact(2, 8) == pytest.approx(0.109375)


# --- committed data ----------------------------------------------------------------------


@pytest.mark.parametrize("split", benchmark.SPLITS)
def test_committed_benchmark_projects_are_well_formed(split):
    for project in benchmark.load_split(split, ROOT / benchmark.DATASET_ROOT):
        result = benchmark.validate(project, run_tests=False)
        assert result.ok, (project.name, result.problems)

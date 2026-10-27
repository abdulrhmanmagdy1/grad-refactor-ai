"""Project review mode: the coordinator with a scripted model, and the project test runner."""

from __future__ import annotations

import io
import json
import textwrap
import zipfile

import pytest

from refactor_ai.contracts import (
    Disposition,
    GenerationResult,
    ModelReference,
    ProviderError,
    ProviderErrorCode,
    ProviderMode,
)
from refactor_ai.project.models import Category
from refactor_ai.project.review import ProjectReviewer, ReviewSettings
from refactor_ai.project.testrun import ProjectTestRunner, TestReport, compare, parse_report
from refactor_ai.project.workspace import extract_project

MODEL = ModelReference(model_id="scripted/model", model_revision="b" * 40)


def code(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


CALC = code(
    """
    def average(values=[]):
        total = 0
        for value in values:
            total += value
        return total / len(values)


    def grade(score):
        if score >= 0:
            if score >= 50:
                return "pass"
            return "fail"
        else:
            raise ValueError("negative score")
    """
)

TESTS = code(
    """
    from app.calc import average, grade


    def test_average():
        assert average([2, 4]) == 3


    def test_grade():
        assert grade(70) == "pass" and grade(10) == "fail"
    """
)

FIXED_AVERAGE = code(
    """
    def average(values=None):
        if values is None:
            values = []
        total = 0
        for value in values:
            total += value
        return total / len(values)
    """
)


def project_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture
def workspace(tmp_path):
    files = {"app/__init__.py": "", "app/calc.py": CALC, "tests/test_calc.py": TESTS}
    return extract_project(project_zip(files), tmp_path / "ws")


class ScriptedProvider:
    """Answers each agent from a script keyed by words of its prompt; records the calls."""

    def __init__(self, answers: dict[str, str] | None = None, fail: set[str] | None = None):
        self.answers = {
            "Assess the architecture": json.dumps(
                {
                    "summary": "Two small modules.",
                    "issues": [
                        {
                            "title": "Uses external libraries",
                            "modules": ["app.calc"],
                            "problem": "It depends on external packages.",
                            "severity": "high",
                        },
                        {
                            "title": "Too many responsibilities",
                            "modules": ["app.calc"],
                            "problem": "It mixes statistics and grading.",
                            "severity": "medium",
                        },
                        {
                            "title": "Unknown module",
                            "modules": ["nowhere"],
                            "problem": "Not in the map.",
                        },
                    ],
                }
            ),
            "claims this architecture problem": '{"verdict": "not_a_problem", "reason": "small"}',
            "Find real bugs in the Python function `average`": json.dumps(
                {
                    "findings": [
                        {
                            "line": 5,
                            "code": "return total / len(values)",
                            "problem": "Division by zero when values is empty.",
                            "severity": "high",
                        },
                        {"line": 2, "code": "this is not in the file", "problem": "invented"},
                    ]
                }
            ),
            "Find real bugs": '{"findings": []}',
            "Write at most 3 pytest test functions": "No tests for this one.",
            "A test written from the documentation": '{"reason": "-", "verdict": "test_wrong"}',
            "security and code-quality": '{"findings": []}',
            "A reviewer claims this problem": '{"verdict": "real", "reason": "yes"}',
            # The fix reviewer's prompt also quotes the problem, so it is matched first.
            "Proposed change": '{"verdict": "accept", "reasons": ["Only the default changes."]}',
            "mutable data structures": f"```python\n{FIXED_AVERAGE}```\nExplanation: default None.",
            "Division by zero": "I would rather not.",
        }
        self.answers.update(answers or {})
        self.fail = fail or set()
        self.prompts: list[str] = []

    @property
    def mode(self) -> ProviderMode:
        return ProviderMode.LOCAL_MODEL

    def generate(self, request) -> GenerationResult:
        prompt = request.messages[-1].content
        self.prompts.append(prompt)
        for key, answer in self.answers.items():
            if key in prompt:
                if key in self.fail:
                    return GenerationResult(
                        provider_mode=self.mode,
                        elapsed_s=0.01,
                        finish_reason="error",
                        error=ProviderError(code=ProviderErrorCode.TIMEOUT, message="slow"),
                    )
                return GenerationResult(
                    text=answer,
                    provider_mode=self.mode,
                    elapsed_s=0.01,
                    model=MODEL,
                    prompt_tokens=10,
                    completion_tokens=5,
                    finish_reason="stop",
                )
        raise AssertionError(f"no scripted answer for: {prompt[:80]}")


def by_source(findings):
    return {f.source: f for f in findings}


# --- coordinator ------------------------------------------------------------------------


def test_static_only_review_without_a_model(workspace):
    outcome = ProjectReviewer(workspace, provider=None).run()
    sources = by_source(outcome.findings)
    assert "static:ruff:B006" in sources and "static:task:guard_clauses" in sources
    assert outcome.calls == [] and outcome.summary["used_model"] is False
    assert "No language model is configured" in outcome.warnings[0]
    assert [f.id for f in outcome.findings] == [
        f"F{i:03d}" for i in range(1, len(outcome.findings) + 1)
    ]
    [fix] = outcome.fixes  # only the deterministic guard-clause rewrite without a model
    assert fix.symbol == "grade" and fix.produced_by == "deterministic:guard_clauses"
    assert fix.syntax.status == "pass" and fix.static_recheck.status == "pass"
    assert fix.tests.status == "not_run" and fix.disposition is Disposition.UNCERTAIN
    assert sources["static:ruff:B006"].recommendation.startswith("Use None as the default")
    assert [stage.stage for stage in outcome.stage_times] == ["index", "static", "fixes"]


def test_full_review_with_agents_tests_and_fixes(workspace):
    provider = ScriptedProvider()
    outcome = ProjectReviewer(
        workspace,
        provider,
        ReviewSettings(run_tests=True),
        test_runner=ProjectTestRunner(),
    ).run()
    summary = outcome.summary
    assert summary["used_model"] is True and outcome.model == MODEL
    assert summary["model_findings"] == {
        "reported": 2,
        "dropped_unquoted": 1,
        "dropped_by_checker": 0,
        "kept": 1,
    }
    assert outcome.architecture["agent_summary"] == "Two small modules."
    # stdlib-only "external" issue and the checker-rejected issue are dropped
    assert outcome.architecture["dropped_agent_issues"] == [
        "Uses external libraries",
        "Too many responsibilities",
    ]
    [unquoted] = outcome.dropped  # kept for evaluation, with the agent's raw item
    assert unquoted["agent"] == "bug_finder" and unquoted["item"]["problem"] == "invented"
    division = next(f for f in outcome.findings if f.source == "agent:bug_finder")
    assert division.category is Category.BUG and division.line_start == 5
    assert division.also_reported_by == ["agent:finding_checker"] and division.fixable
    assert outcome.baseline_tests["status"] == "ran" and outcome.baseline_tests["passed"] == 2

    fixes = {fix.symbol: fix for fix in outcome.fixes}
    average = fixes["average"]
    b006 = by_source(outcome.findings)["static:ruff:B006"]
    assert average.finding_ids == [b006.id]  # the division fix had no code; B006 was fixed
    assert "Division by zero" not in (average.explanation or "")
    assert "Not fixed" in average.static_recheck.detail
    assert average.syntax.status == "pass" and average.static_recheck.status == "pass"
    assert average.tests.status == "pass" and average.review.status == "accept"
    assert average.disposition is Disposition.PROPOSAL_READY
    assert "+def average(values=None):" in average.diff
    grade = fixes["grade"]
    assert grade.tests.status == "pass" and grade.review.status == "not_run"
    assert grade.disposition is Disposition.PROPOSAL_READY
    roles = [call.role for call in outcome.calls]
    assert roles[0] == "architecture" and roles.count("fix_reviewer") == 1
    assert all(call.status == "ok" for call in outcome.calls)


def test_fixes_that_add_findings_or_break_tests_are_rejected(workspace):
    # The scripted fixer's answer is text for the static re-check; it is never executed.
    adds_eval = code(
        """
        def average(values=None):
            return eval("sum(values) / len(values)")
        """
    )
    provider = ScriptedProvider(
        {"mutable data structures": f"```python\n{adds_eval}```\nExplanation: shorter."}
    )
    outcome = ProjectReviewer(workspace, provider).run()
    average = next(fix for fix in outcome.fixes if fix.symbol == "average")
    assert average.static_recheck.status == "fail" and "S307" in average.static_recheck.detail
    assert average.disposition is Disposition.REJECTED

    breaks = code(
        """
        def average(values=None):
            values = values or []
            return 0
        """
    )
    provider = ScriptedProvider(
        {"mutable data structures": f"```python\n{breaks}```\nExplanation: x."}
    )
    outcome = ProjectReviewer(
        workspace, provider, ReviewSettings(run_tests=True), test_runner=ProjectTestRunner()
    ).run()
    average = next(fix for fix in outcome.fixes if fix.symbol == "average")
    assert average.tests.status == "fail" and "test_average" in average.tests.detail
    assert average.disposition is Disposition.REJECTED


def test_untested_function_and_review_doubt_make_a_fix_uncertain(tmp_path):
    files = {
        "app/__init__.py": "",
        "app/calc.py": CALC,
        "tests/test_other.py": "def test_x():\n    assert True\n",
    }
    workspace = extract_project(project_zip(files), tmp_path / "ws")
    provider = ScriptedProvider({"Proposed change": '{"verdict": "uncertain", "reasons": []}'})
    outcome = ProjectReviewer(
        workspace, provider, ReviewSettings(run_tests=True), test_runner=ProjectTestRunner()
    ).run()
    average = next(fix for fix in outcome.fixes if fix.symbol == "average")
    assert average.tests.status == "not_available" and "No test refers to average()" in (
        average.tests.detail
    )
    assert average.disposition is Disposition.UNCERTAIN
    reasons = " ".join(average.disposition_reasons)
    assert "tests_not_available" in reasons and "review_uncertain" in reasons


def test_a_fix_only_the_agents_ask_for_needs_a_test_to_be_ready(tmp_path):
    stats = (
        'def ratio(part, whole):\n    """part as a share of whole."""\n    return part / whole\n'
    )
    tests = "from app.stats import ratio\n\n\ndef test_ratio():\n    assert ratio(1, 2) == 0.5\n"
    claim = {
        "line": 3,
        "code": "return part / whole",
        "problem": "Division by zero when whole is 0.",
    }
    guarded = (
        "```python\ndef ratio(part, whole):\n    if whole == 0:\n        return 0.0\n"
        "    return part / whole\n```\nExplanation: guard the empty whole."
    )

    def review(extra_test: str):
        files = {
            "app/__init__.py": "",
            "app/stats.py": stats,
            "tests/test_stats.py": tests + extra_test,
        }
        workspace = extract_project(project_zip(files), tmp_path / f"ws{len(extra_test)}")
        provider = ScriptedProvider({"Division by zero": guarded})
        provider.answers = {  # matched before the generic "Find real bugs" answer
            "Find real bugs in the Python function `ratio`": json.dumps({"findings": [claim]}),
            **provider.answers,
        }
        settings = ReviewSettings(run_tests=True)
        runner = ProjectTestRunner()
        outcome = ProjectReviewer(workspace, provider, settings, test_runner=runner).run()
        return next(fix for fix in outcome.fixes if fix.symbol == "ratio")

    fix = review("")
    assert (fix.syntax.status, fix.static_recheck.status) == ("pass", "pass")
    assert (fix.tests.status, fix.review.status) == ("pass", "accept")
    # Every check passed, but only the model says the change is needed.
    assert fix.disposition is Disposition.UNCERTAIN
    assert [reason.split(":")[0] for reason in fix.disposition_reasons] == ["model_only"]
    exposing = "\n\ndef test_ratio_of_nothing():\n    assert ratio(1, 0) == 0.0\n"
    assert review(exposing).disposition is Disposition.PROPOSAL_READY


CLAMP = (
    "def clamp(value, low, high):\n"
    '    """value limited to low..high, both ends included."""\n'
    "    if value < low:\n"
    "        return low\n"
    "    if value >= high:\n"
    "        return high - 1\n"
    "    return value\n"
)
CLAMP_TESTS = "from app.limits import clamp\n\n\ndef test_low():\n    assert clamp(-1, 0, 5) == 0\n"
SPEC_ANSWER = (
    "```python\nfrom app.limits import clamp\n\n\n"
    "def test_spec_1():\n    assert clamp(3, 0, 5) == 3\n"
    "\n\ndef test_spec_2():\n    assert clamp(9, 0, 5) == 5\n\n\ndef test_spec_3():\n"
    "    assert clamp(2, 0, 5) == 99\n```"
)
FIXED_CLAMP = (
    "```python\ndef clamp(value, low, high):\n"
    '    """value limited to low..high, both ends included."""\n'
    "    if value < low:\n        return low\n    if value > high:\n        return high\n"
    "    return value\n```\nExplanation: include the upper end."
)


def spec_review(tmp_path, verdicts: dict[str, str], first_answer: str = SPEC_ANSWER):
    files = {"app/__init__.py": "", "app/limits.py": CLAMP, "tests/test_limits.py": CLAMP_TESTS}
    workspace = extract_project(project_zip(files), tmp_path / "ws")
    provider = ScriptedProvider(
        {
            "could not check it": SPEC_ANSWER,
            "Write at most 3 pytest test functions": first_answer,
            "does not do what its documentation says": FIXED_CLAMP,
        }
    )

    def check(test: str) -> str:
        return json.dumps({"reason": f"about {test}", "verdict": verdicts.get(test, "test_wrong")})

    # The checker prompt shows the failing test in a code block, so each test gets its own
    # verdict (the fixer's prompt quotes the test without the block).
    provider.answers = {
        **{f"```python\ndef {test}": check(test) for test in ("test_spec_2", "test_spec_3")},
        **provider.answers,
    }
    settings = ReviewSettings(run_tests=True)
    reviewer = ProjectReviewer(workspace, provider, settings, test_runner=ProjectTestRunner())
    return reviewer, reviewer.run()


def test_spec_tests_show_a_bug_the_finders_missed_and_prove_its_fix(tmp_path):
    reviewer, outcome = spec_review(tmp_path, {"test_spec_2": "code_wrong"})
    [spec] = [f for f in outcome.findings if f.source == "agent:spec_tester"]
    assert spec.symbol == "clamp" and spec.category is Category.BUG and spec.fixable
    assert "test_spec_2" in spec.explanation and spec.line_start == 1 and spec.line_end == 7
    # The passing test and the blamed one are kept; the test blamed on itself is dropped.
    [kept] = reviewer.spec_files.values()
    assert "test_spec_1" in kept and "test_spec_2" in kept and "test_spec_3" not in kept
    assert {d.get("spec_test") for d in outcome.dropped if "spec_test" in d} == {"test_spec_3"}
    assert outcome.summary["model_findings"]["spec_blamed_on_code"] == 1
    fix = next(f for f in outcome.fixes if f.symbol == "clamp")
    # test_spec_2 fails before the fix and passes after it: evidence, so the fix is ready.
    assert fix.tests.status == "pass" and fix.disposition is Disposition.PROPOSAL_READY
    roles = [call.role for call in outcome.calls]
    assert roles.count("spec_tester") == 1 and roles.count("spec_checker") == 2


def test_a_failing_spec_test_blamed_on_itself_is_no_finding(tmp_path):
    reviewer, outcome = spec_review(tmp_path, {})
    assert not [f for f in outcome.findings if f.source == "agent:spec_tester"]
    [kept] = reviewer.spec_files.values()  # only the passing test is kept
    assert "test_spec_1" in kept and "test_spec_2" not in kept


def test_a_fix_that_closes_an_import_cycle_is_rejected(tmp_path):
    files = {
        "README.md": "Averages are taken over the values given.",
        "app/__init__.py": "",
        "app/calc.py": CALC,
        "app/report.py": "from app.calc import average\n\n\ndef summary(values):\n"
        "    return round(average(values), 1)\n",
        "tests/test_calc.py": TESTS,
    }
    workspace = extract_project(project_zip(files), tmp_path / "ws")
    cyclic = f"```python\nfrom app.report import summary\n\n{FIXED_AVERAGE}```\nExplanation: ok."
    provider = ScriptedProvider({"mutable data structures": cyclic})
    outcome = ProjectReviewer(workspace, provider).run()
    average = next(fix for fix in outcome.fixes if fix.symbol == "average")
    assert average.disposition is Disposition.REJECTED and average.proposed is None
    assert "app.report imports app.calc back" in average.static_recheck.detail
    finder_prompts = [p for p in provider.prompts if "Find real bugs" in p]
    assert finder_prompts and all("Averages are taken over" in p for p in finder_prompts)


def test_findings_the_checker_drops_are_recorded(workspace):
    provider = ScriptedProvider(
        {"A reviewer claims this problem": '{"verdict": "not_a_problem", "reason": "fine"}'}
    )
    outcome = ProjectReviewer(workspace, provider, ReviewSettings(max_findings_checked=0)).run()
    assert outcome.summary["model_findings"]["dropped_by_checker"] == 1
    assert [entry.get("reason") for entry in outcome.dropped] == [None, "not_checked"]
    outcome = ProjectReviewer(workspace, ScriptedProvider(provider.answers)).run()
    dropped = [entry for entry in outcome.dropped if "finding" in entry]
    assert [entry["reason"] for entry in dropped] == ["checker:not_a_problem"]
    assert dropped[0]["finding"]["line_start"] == 5
    assert not any(f.source == "agent:bug_finder" for f in outcome.findings)


def test_failed_calls_and_the_call_budget(workspace):
    provider = ScriptedProvider(fail={"Assess the architecture"})
    outcome = ProjectReviewer(workspace, provider, ReviewSettings(max_calls=3)).run()
    assert len(outcome.calls) == 3
    assert outcome.calls[0].status == "error" and "timeout" in outcome.calls[0].error
    assert any("budget" in warning for warning in outcome.warnings)
    average = next(fix for fix in outcome.fixes if fix.symbol == "average")
    assert average.disposition is Disposition.FAILED and average.proposed is None


def test_unreadable_agent_answers_are_warned_and_skipped(workspace):
    provider = ScriptedProvider({"Assess the architecture": "no json at all"})
    outcome = ProjectReviewer(workspace, provider).run()
    assert "The architecture reviewer's answer could not be read." in outcome.warnings


def test_progress_is_reported(workspace):
    seen = []
    ProjectReviewer(
        workspace, None, on_progress=lambda status, text: seen.append(status.value)
    ).run()
    assert seen[:2] == ["indexing", "scanning"] and seen[-1] == "fixing"


# --- project test runner ------------------------------------------------------------------


SAFETY_TESTS = code(
    """
    import os
    import socket
    import subprocess
    import sys


    def test_network_is_blocked():
        try:
            socket.create_connection(("example.com", 80), timeout=2)
        except PermissionError:
            return
        raise AssertionError("network was allowed")


    def test_processes_are_blocked():
        try:
            subprocess.run([sys.executable, "-c", "pass"])
        except PermissionError:
            return
        raise AssertionError("a process was started")


    def test_writes_outside_are_blocked(tmp_path):
        (tmp_path / "inside.txt").write_text("ok")
        outside = os.path.join(os.path.dirname(os.getcwd()), "..", "escape.txt")
        try:
            open(outside, "w")
        except PermissionError:
            return
        raise AssertionError("a write outside the copy was allowed")
    """
)


def test_runner_blocks_network_processes_and_outside_writes(tmp_path):
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "test_safety.py").write_text(SAFETY_TESTS, encoding="utf-8")
    report = ProjectTestRunner().run(tmp_path / "proj")
    assert report.status == "ran", report.detail
    assert len(report.passed) == 3 and not report.failed and not report.errors


def test_runner_compares_before_and_after(workspace):
    runner = ProjectTestRunner()
    baseline = runner.run(workspace.root)
    assert baseline.status == "ran" and len(baseline.passed) == 2
    broken = runner.run(workspace.root, {"app/calc.py": CALC.replace('return "pass"', "return 0")})
    status, detail = compare(baseline, broken)
    assert status == "fail" and "test_grade" in detail
    assert (workspace.root / "app" / "calc.py").read_text(encoding="utf-8") == CALC


def test_runner_timeouts_no_tests_and_replacements_outside(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "test_slow.py").write_text(
        "import time\n\n\ndef test_slow():\n    time.sleep(30)\n", encoding="utf-8"
    )
    assert ProjectTestRunner(wall_s=3).run(project).status == "timeout"
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "mod.py").write_text("x = 1\n", encoding="utf-8")
    assert ProjectTestRunner().run(empty).status == "no_tests"
    with pytest.raises(ValueError, match="outside"):
        ProjectTestRunner().run(empty, {"../evil.py": "x = 1\n"})
    with pytest.raises(ValueError, match="outside"):
        ProjectTestRunner().run(empty, targets=("../other",))


def test_runner_can_run_selected_test_files(workspace):
    extra = "def test_extra():\n    assert True\n"
    report = ProjectTestRunner().run(
        workspace.root, {"test_extra.py": extra}, targets=("test_extra.py",)
    )
    assert report.status == "ran" and report.passed == {"test_extra::test_extra"}
    assert not (workspace.root / "test_extra.py").exists()


def test_compare_statuses():
    baseline = TestReport(status="ran", passed={"a", "b"}, failed={"c"})
    assert compare(baseline, TestReport(status="ran", passed={"a", "b", "c"}))[0] == "pass"
    assert (
        "fail before the fix and pass after"
        in compare(baseline, TestReport(status="ran", passed={"a", "b", "c"}))[1]
    )
    assert compare(baseline, TestReport(status="ran", passed={"a"}))[0] == "fail"
    assert compare(baseline, TestReport(status="timeout"))[0] == "fail"
    assert compare(baseline, TestReport(status="error", detail="boom")) == ("error", "boom")


def test_parse_report_refuses_doctypes_and_reads_results(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text(
        '<!DOCTYPE x [<!ENTITY a "b">]><testsuite><testcase classname="t" name="a"/></testsuite>'
    )
    assert parse_report(path) is None
    path.write_text(
        "<testsuites><testsuite>"
        '<testcase classname="t" name="ok"/>'
        '<testcase classname="t" name="bad"><failure message="x"/></testcase>'
        '<testcase classname="t" name="err"><error message="x"/></testcase>'
        '<testcase classname="t" name="skip"><skipped/></testcase>'
        "</testsuite></testsuites>"
    )
    report = parse_report(path)
    assert report.passed == {"t::ok"} and report.failed == {"t::bad"}
    assert report.errors == {"t::err"} and report.skipped == 1
    assert report.messages == {"t::bad": "x", "t::err": "x"}
    assert parse_report(tmp_path / "missing.xml") is None
    long = "y" * 5000
    path.write_text(
        "<testsuite>"
        f'<testcase classname="t" name="bad"><failure message="assert 1 == 2">{long}tail'
        "</failure></testcase></testsuite>"
    )
    message = parse_report(path).messages["t::bad"]
    assert message.startswith("assert 1 == 2") and message.endswith("tail")
    assert len(message) <= 800


def test_spec_tests_that_call_the_code_wrongly_get_one_repair(tmp_path):
    # The first tests call clamp with two arguments: a TypeError, not evidence.
    wrong = SPEC_ANSWER.replace("clamp(9, 0, 5)", "clamp(9, 5)")
    reviewer, outcome = spec_review(tmp_path, {"test_spec_2": "code_wrong"}, wrong)
    assert outcome.summary["model_findings"]["spec_repaired"] == 1
    assert [f.symbol for f in outcome.findings if f.source == "agent:spec_tester"] == ["clamp"]
    tester_calls = [c.target for c in outcome.calls if c.role == "spec_tester"]
    assert tester_calls == ["app/limits.py:clamp", "app/limits.py:clamp:repair"]

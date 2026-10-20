import itertools

import pytest

from refactor_ai.contracts import (
    Disposition,
    ModelReviewResult,
    ReferenceCase,
    ReferenceTest,
    ReferenceTestFailure,
    ReferenceTestsResult,
    RubricCheck,
    RunnerInfo,
    SyntaxCheck,
    WorkflowMode,
)
from refactor_ai.tasks import guard_clauses
from refactor_ai.verification import checks, disposition, policy
from refactor_ai.verification.diffing import changed_lines, source_lines, unified_diff

ORIGINAL = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight > 0:
        if express:
            return weight * 3
        else:
            return weight * 2
    else:
        raise ValueError("weight must be positive")
'''
GOOD = guard_clauses.to_guard_clauses(ORIGINAL)
CASE = ReferenceCase(
    case_id="shipping",
    task_type="guard_clauses",
    function_name="shipping_cost",
    original_code=ORIGINAL,
    tests=[ReferenceTest(args="[2, True]", expect={"kind": "return", "value": "6"})],
)
PASS = ReferenceTestsResult(
    status="pass", case_id="shipping", total=1, passed=1, failed=0, errored=0
)


class RecordingRunner:
    def __init__(self, result=PASS, accepts_timeout=False):
        self.result = result
        self.calls = []
        if accepts_timeout:
            self.accepts_timeout = True

    def info(self):
        return RunnerInfo(enabled=True)

    def run(self, case, candidate_code, **kwargs):
        self.calls.append((candidate_code, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


# --- Syntax and rubric ----------------------------------------------------------------


def test_syntax_pass_and_fail():
    assert checks.check_syntax(GOOD) == SyntaxCheck(status="pass")
    failed = checks.check_syntax("def f(x):\n    if x\n        return 1\n")
    assert failed.status == "fail" and "line 2" in failed.error
    assert checks.check_syntax("def f(:\n").error.startswith("invalid syntax")
    null = checks.check_syntax("def f():\n    return '\x00'\n")
    assert null.status == "fail"


def test_rubric_pass_fail_and_not_run():
    passed = checks.check_rubric(ORIGINAL, GOOD, SyntaxCheck(status="pass"))
    assert passed.status == "pass" and all(passed.checks.values())
    failed = checks.check_rubric(ORIGINAL, ORIGINAL, SyntaxCheck(status="pass"))
    assert failed.status == "fail" and failed.checks["nesting_reduced"] is False
    skipped = checks.check_rubric(ORIGINAL, "def f(:\n", SyntaxCheck(status="fail", error="x"))
    assert skipped.status == "not_run" and skipped.reasons == [checks.RUBRIC_SKIPPED]


def test_rubric_reasons_describe_the_proposal():
    two = GOOD + "\ndef helper():\n    return 1\n"
    result = checks.check_rubric(ORIGINAL, two, checks.check_syntax(two))
    assert result.reasons == ["The proposal must contain exactly one top-level function only."]


# --- Reference test gating -------------------------------------------------------------


def gate(candidate, case=CASE, runner=None, timeout_s=None):
    syntax = checks.check_syntax(candidate)
    rubric = checks.check_rubric(ORIGINAL, candidate, syntax)
    return checks.run_reference_tests(
        case, candidate, runner=runner, syntax=syntax, rubric=rubric, timeout_s=timeout_s
    )


def test_no_case_is_not_available():
    result = gate(GOOD, case=None, runner=RecordingRunner())
    assert result.status == "not_available" and result.reason == checks.NO_CASE


def test_case_without_tests_is_not_available():
    runner = RecordingRunner()
    result = gate(GOOD, case=CASE.model_copy(update={"tests": []}), runner=runner)
    assert result.status == "not_available" and runner.calls == []


def test_missing_runner_is_not_run():
    result = gate(GOOD, runner=None)
    assert result.status == "not_run" and result.reason == checks.NO_RUNNER


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        ("def shipping_cost(:\n", checks.NOT_PARSED),
        ("import os\n" + GOOD, checks.OUT_OF_SCOPE),
        (GOOD.replace("return weight * 3", "return __import__('os')"), checks.OUT_OF_SCOPE),
        (GOOD + "\nx = 1\n", checks.OUT_OF_SCOPE),
    ],
)
def test_candidates_are_gated_before_execution(candidate, reason):
    runner = RecordingRunner()
    result = gate(candidate, runner=runner)
    assert result.status == "not_run" and result.reason == reason
    assert runner.calls == []


def test_rubric_failure_alone_still_runs_tests():
    runner = RecordingRunner()
    result = gate(ORIGINAL, runner=runner)
    assert result == PASS and runner.calls == [(ORIGINAL, {})]


def test_runner_exception_becomes_error():
    result = gate(GOOD, runner=RecordingRunner(result=RuntimeError("boom")))
    assert result.status == "error" and result.reason == checks.RUNNER_CRASHED


def test_runner_returning_garbage_becomes_error():
    result = gate(GOOD, runner=RecordingRunner(result={"status": "pass"}))
    assert result.status == "error"


def test_timeout_is_passed_only_to_runners_that_accept_it():
    plain = RecordingRunner()
    gate(GOOD, runner=plain, timeout_s=3.0)
    assert plain.calls == [(GOOD, {})]
    aware = RecordingRunner(accepts_timeout=True)
    gate(GOOD, runner=aware, timeout_s=3.0)
    assert aware.calls == [(GOOD, {"timeout_s": 3.0})]


def test_run_checks_and_failed_property():
    good = checks.run_checks(ORIGINAL, GOOD, case=CASE, runner=RecordingRunner())
    assert not good.failed
    broken = checks.run_checks(ORIGINAL, "def f(:\n", case=CASE, runner=RecordingRunner())
    assert broken.failed and broken.tests.status == "not_run"
    erroring = checks.run_checks(
        ORIGINAL, GOOD, case=CASE, runner=RecordingRunner(ReferenceTestsResult(status="error"))
    )
    assert erroring.failed


def test_describe_checks():
    failing = ReferenceTestsResult(
        status="fail",
        total=3,
        passed=2,
        failed=1,
        errored=0,
        failures=[ReferenceTestFailure(index=1, kind="wrong_value", detail="f(1) returned\n2")],
    )
    result = checks.DeterministicChecks(
        syntax=SyntaxCheck(status="pass"),
        rubric=RubricCheck(status="fail", reasons=["The docstring changed."]),
        tests=failing,
    )
    assert checks.describe_checks(result) == [
        "syntax: pass",
        "rubric: fail (The docstring changed.)",
        "reference tests: fail (2 of 3 passed)",
        "test 1 wrong_value: f(1) returned 2",
    ]
    missing = checks.DeterministicChecks(
        syntax=SyntaxCheck(status="fail", error="invalid syntax (line 1)"),
        rubric=RubricCheck(status="not_run"),
        tests=ReferenceTestsResult(status="not_run", reason="not parsed"),
    )
    assert checks.describe_checks(missing) == [
        "syntax: fail (invalid syntax (line 1))",
        "rubric: not_run",
        "reference tests: not_run (not parsed)",
    ]


# --- Disposition ----------------------------------------------------------------------

SYNTAX = {
    status: SyntaxCheck(status=status, error="e" if status == "fail" else None)
    for status in ("pass", "fail", "not_run")
}
RUBRIC = {
    status: RubricCheck(status=status, reasons=["r"] if status == "fail" else [])
    for status in ("pass", "fail", "not_run")
}
TESTS = {
    "pass": PASS,
    "fail": ReferenceTestsResult(status="fail", total=1, passed=0, failed=1, errored=0),
    "error": ReferenceTestsResult(status="error", reason="crash"),
    "not_available": ReferenceTestsResult(status="not_available", reason="none"),
    "not_run": ReferenceTestsResult(status="not_run", reason="disabled"),
}
REVIEW = {
    status: ModelReviewResult(status=status)
    for status in ("accept", "reject", "uncertain", "error", "not_run")
}


def expected_disposition(syntax, rubric, tests, review, mode):
    if syntax == "fail" or rubric == "fail" or tests in ("fail", "error") or review == "reject":
        return Disposition.REJECTED
    if (
        syntax != "pass"
        or rubric != "pass"
        or review in ("uncertain", "error")
        or (review == "not_run" and mode == WorkflowMode.MULTI_ROLE)
        or tests in ("not_available", "not_run")
    ):
        return Disposition.UNCERTAIN
    return Disposition.PROPOSAL_READY


@pytest.mark.parametrize(
    ("syntax", "rubric", "tests", "review", "mode"),
    list(itertools.product(SYNTAX, RUBRIC, TESTS, REVIEW, list(WorkflowMode))),
)
def test_disposition_order(syntax, rubric, tests, review, mode):
    result, reasons = disposition.decide(
        SYNTAX[syntax], RUBRIC[rubric], TESTS[tests], REVIEW[review], mode=mode
    )
    assert result == expected_disposition(syntax, rubric, tests, review, mode)
    assert reasons
    for item in reasons:
        code, _, text = item.partition(": ")
        assert code in disposition.REASON_CODES and text


def test_model_accept_never_overrides_a_failed_check():
    for broken in ("syntax", "rubric", "tests"):
        parts = {"syntax": SYNTAX["pass"], "rubric": RUBRIC["pass"], "tests": TESTS["pass"]}
        parts[broken] = {"syntax": SYNTAX, "rubric": RUBRIC, "tests": TESTS}[broken]["fail"]
        result, _ = disposition.decide(
            parts["syntax"],
            parts["rubric"],
            parts["tests"],
            REVIEW["accept"],
            mode=WorkflowMode.MULTI_ROLE,
        )
        assert result == Disposition.REJECTED


@pytest.mark.parametrize(
    "tests",
    [
        ReferenceTestsResult(status="pass"),
        ReferenceTestsResult(status="pass", total=0, passed=0),
        ReferenceTestsResult(status="pass", total=3, passed=2),
    ],
)
def test_pass_without_complete_counts_is_not_a_pass(tests):
    result, reasons = disposition.decide(
        SYNTAX["pass"], RUBRIC["pass"], tests, REVIEW["accept"], mode=WorkflowMode.MULTI_ROLE
    )
    assert result == Disposition.UNCERTAIN
    assert reasons[0].startswith("tests_not_available: ")


def test_rejected_lists_every_failure():
    _, reasons = disposition.decide(
        SYNTAX["pass"],
        RUBRIC["fail"],
        TESTS["fail"],
        REVIEW["reject"],
        mode=WorkflowMode.MULTI_ROLE,
    )
    assert [item.partition(":")[0] for item in reasons] == [
        "rubric_fail",
        "tests_fail",
        "review_reject",
    ]
    assert reasons[1] == "tests_fail: 1 of 1 reference tests failed."


def test_ready_reason_states_the_limits_of_testing():
    result, reasons = disposition.decide(
        SYNTAX["pass"], RUBRIC["pass"], PASS, REVIEW["not_run"], mode=WorkflowMode.SINGLE_ROLE
    )
    assert result == Disposition.PROPOSAL_READY
    assert reasons == [
        "ready: Syntax and rubric passed, 1 of 1 reference tests passed and no model review is "
        "part of the single-role workflow. Passing tests does not prove equal behavior for "
        "every input."
    ]


def test_reason_is_bounded_and_single_line():
    text = disposition.reason("tests_error", "line one\nline two " + "x" * 1000)
    assert "\n" not in text and len(text) <= len("tests_error: ") + disposition.MAX_REASON_CHARS


def test_not_run_verification_only_for_no_change_and_failed():
    result = disposition.not_run_verification(Disposition.FAILED, ["timeout: slow"])
    assert (
        result.syntax.status == "not_run"
        and result.reference_tests.reason == "No proposal to test."
    )
    with pytest.raises(ValueError):
        disposition.not_run_verification(Disposition.REJECTED, [])


# --- Diff -----------------------------------------------------------------------------


def test_unified_diff_and_changed_lines():
    diff = unified_diff(ORIGINAL, GOOD)
    assert diff.startswith("--- original.py\n+++ proposed.py\n@@ -1,9 +1,7 @@\n")
    assert "-    if weight > 0:\n" in diff and "+    if weight <= 0:\n" in diff
    assert changed_lines(ORIGINAL, GOOD) == [3, 4, 5, 6, 7]


def test_identical_code_has_no_diff():
    assert unified_diff(ORIGINAL, ORIGINAL) == ""
    assert changed_lines(ORIGINAL, ORIGINAL) == []


def test_line_endings_are_normalized():
    assert unified_diff(ORIGINAL.replace("\n", "\r\n"), ORIGINAL) == ""
    assert unified_diff(ORIGINAL.rstrip("\n"), ORIGINAL) == ""


def test_inserted_lines_are_reported_in_proposal_numbering():
    assert changed_lines("a\nb\n", "a\nx\nb\n") == [2]
    assert changed_lines("a\nb\nc\n", "a\nc\n") == []
    assert changed_lines("a\n", "b\n") == [1]


def test_source_lines_follow_python_line_breaks():
    assert source_lines("a\fb\nc d\r\ne\rf") == ["a\fb\n", "c d\n", "e\n", "f\n"]
    assert source_lines("") == []
    assert source_lines("\n") == ["\n"]


# --- Runner admission policy ---------------------------------------------------------


@pytest.mark.parametrize(
    ("candidate", "problems"),
    [
        (GOOD, []),
        ("def f(:\n", ["syntax_error"]),
        ("import os\n" + GOOD, ["not_single_function"]),
        ("def f(x):\n    import os\n    return x\n", ["imports_present"]),
        ("def f(x):\n    g = eval\n    return g(x)\n", ["denied_name:eval"]),
        ("def f(x):\n    return open\n", ["denied_name:open"]),
        ("def f(input):\n    return input + 1\n", []),
        ("def f(x):\n    vars = [x]\n    return vars\n", []),
        ("def f(x):\n    return [print for print in x]\n", []),
        ("def f(x):\n    return getattr(x, 'real', 0)\n", []),
        ("def f(x):\n    return hasattr(x, 'append')\n", []),
        ("def f(x, name):\n    return getattr(x, name)\n", ["dynamic_attribute_access"]),
        ("def f(x):\n    return getattr(x, '_' * 2 + 'class__')\n", ["dynamic_attribute_access"]),
        ("def f(x):\n    return getattr(x, '_private')\n", ["dynamic_attribute_access"]),
        ("def f(x):\n    return getattr(x)\n", ["dynamic_attribute_access"]),
        ("def f(x):\n    return getattr(x, name='real')\n", ["dynamic_attribute_access"]),
        ("def f(x):\n    return x.__class__\n", ["dunder_access"]),
        ("def f(x):\n    exec('x')\n    return x\n", ["denied_call:exec"]),
        ("def f(x):\n    getattr = len\n    return getattr(x, y)\n", []),
    ],
)
def test_admission_policy(candidate, problems):
    assert policy.admission_problems(candidate) == problems


def test_policy_descriptions_refer_to_the_candidate():
    assert policy.describe("not_single_function") == (
        "The candidate must contain exactly one top-level function only."
    )
    assert (
        policy.describe("denied_name:eval") == "References to eval are outside the runner policy."
    )
    assert "literal attribute name" in policy.describe("dynamic_attribute_access")
    assert policy.describe("imports_present") == "Imports are outside the supported scope."

"""Deterministic verification of a proposal: syntax, task rubric and reference tests.

Nothing here executes code in the calling process. Syntax is judged with ast.parse only;
the rubric inspects syntax trees; reference tests run only through a ReferenceRunner,
which executes the candidate in a separate, limited process.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass

from refactor_ai.contracts import (
    ReferenceCase,
    ReferenceRunner,
    ReferenceTestsResult,
    RubricCheck,
    SyntaxCheck,
)
from refactor_ai.tasks import guard_clauses

logger = logging.getLogger(__name__)

NO_CASE = "No trusted reference case was selected, so behavior was not tested."
NO_TESTS = "The reference case has no tests."
NO_RUNNER = "No reference runner is configured."
NOT_PARSED = "The proposal is not valid Python, so it was not executed."
OUT_OF_SCOPE = "The proposal is outside the task constraints, so it was not executed."
RUNNER_CRASHED = "The reference runner failed unexpectedly; details were logged."
RUBRIC_SKIPPED = "The rubric was not checked because the proposal does not parse."
MAX_SUMMARY_CHARS = 300


@dataclass(frozen=True)
class DeterministicChecks:
    """The three deterministic dimensions for one candidate."""

    syntax: SyntaxCheck
    rubric: RubricCheck
    tests: ReferenceTestsResult

    @property
    def failed(self) -> bool:
        """True when any deterministic check failed or errored."""
        return (
            self.syntax.status == "fail"
            or self.rubric.status == "fail"
            or self.tests.status in ("fail", "error")
        )


def check_syntax(candidate: str) -> SyntaxCheck:
    """Parse with ast only; never compile to bytecode or execute."""
    try:
        ast.parse(candidate)
    except SyntaxError as exc:
        location = f"line {exc.lineno}" if exc.lineno else "unknown line"
        if exc.lineno and exc.offset:
            location += f", column {exc.offset}"
        return SyntaxCheck(status="fail", error=f"{exc.msg} ({location})")
    except (ValueError, RecursionError, MemoryError) as exc:
        return SyntaxCheck(
            status="fail", error=f"the code could not be parsed ({type(exc).__name__})"
        )
    return SyntaxCheck(status="pass")


def _rubric_reason(text: str) -> str:
    # guard_clauses reason texts describe the submitted input; here they describe a proposal.
    return "The proposal " + text[len("The input ") :] if text.startswith("The input ") else text


def check_rubric(original: str, candidate: str, syntax: SyntaxCheck) -> RubricCheck:
    """The task rubric from guard_clauses; not_run when the proposal does not parse."""
    if syntax.status != "pass":
        return RubricCheck(status="not_run", reasons=[RUBRIC_SKIPPED])
    try:
        result = guard_clauses.rubric(original, candidate)
    except (ValueError, RecursionError, MemoryError) as exc:
        return RubricCheck(
            status="fail",
            reasons=[f"The rubric could not be evaluated ({type(exc).__name__})."],
        )
    return RubricCheck(
        status="pass" if result.passed else "fail",
        checks=dict(result.checks),
        reasons=[_rubric_reason(text) for text in result.reasons],
    )


def run_reference_tests(
    case: ReferenceCase | None,
    candidate: str,
    *,
    runner: ReferenceRunner | None,
    syntax: SyntaxCheck,
    rubric: RubricCheck,
    timeout_s: float | None = None,
) -> ReferenceTestsResult:
    """Trusted reference tests, or an explicit not_available/not_run/error result.

    Candidates that do not parse or that leave the task constraints (imports, dunder
    access, denied calls, nested definitions) are never handed to the runner.
    """
    if case is None:
        return ReferenceTestsResult(status="not_available", reason=NO_CASE)
    if not case.tests:
        return ReferenceTestsResult(status="not_available", case_id=case.case_id, reason=NO_TESTS)
    if runner is None:
        return ReferenceTestsResult(status="not_run", case_id=case.case_id, reason=NO_RUNNER)
    if syntax.status != "pass":
        return ReferenceTestsResult(status="not_run", case_id=case.case_id, reason=NOT_PARSED)
    if (
        rubric.checks.get("parses_as_single_function") is False
        or rubric.checks.get("within_task_constraints") is False
    ):
        return ReferenceTestsResult(status="not_run", case_id=case.case_id, reason=OUT_OF_SCOPE)
    try:
        if timeout_s is not None and getattr(runner, "accepts_timeout", False) is True:
            result = runner.run(case, candidate, timeout_s=timeout_s)  # type: ignore[call-arg]
        else:
            result = runner.run(case, candidate)
    except Exception:
        logger.exception("The reference runner raised for case %s", case.case_id)
        return ReferenceTestsResult(status="error", case_id=case.case_id, reason=RUNNER_CRASHED)
    if not isinstance(result, ReferenceTestsResult):
        logger.error("The reference runner returned %s instead of a result", type(result).__name__)
        return ReferenceTestsResult(status="error", case_id=case.case_id, reason=RUNNER_CRASHED)
    return result


def run_checks(
    original: str,
    candidate: str,
    *,
    case: ReferenceCase | None,
    runner: ReferenceRunner | None,
    timeout_s: float | None = None,
) -> DeterministicChecks:
    syntax = check_syntax(candidate)
    rubric = check_rubric(original, candidate, syntax)
    tests = run_reference_tests(
        case, candidate, runner=runner, syntax=syntax, rubric=rubric, timeout_s=timeout_s
    )
    return DeterministicChecks(syntax=syntax, rubric=rubric, tests=tests)


def _bounded(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_SUMMARY_CHARS else text[: MAX_SUMMARY_CHARS - 3] + "..."


def describe_checks(checks: DeterministicChecks, max_failures: int = 3) -> list[str]:
    """Short single-line summaries of the deterministic results, for role prompts."""
    syntax = checks.syntax
    lines = [_bounded(f"syntax: {syntax.status}" + (f" ({syntax.error})" if syntax.error else ""))]
    rubric = checks.rubric
    if rubric.status == "fail" and rubric.reasons:
        lines.append(_bounded(f"rubric: fail ({'; '.join(rubric.reasons)})"))
    else:
        lines.append(f"rubric: {rubric.status}")
    tests = checks.tests
    if tests.status in ("pass", "fail") and tests.total:
        summary = f"reference tests: {tests.status} ({tests.passed} of {tests.total} passed)"
        lines.append(summary)
        for failure in tests.failures[:max_failures]:
            lines.append(_bounded(f"test {failure.index} {failure.kind}: {failure.detail}"))
    else:
        detail = f" ({tests.reason})" if tests.reason else ""
        lines.append(_bounded(f"reference tests: {tests.status}{detail}"))
    return lines

"""Workflow coordinator tests on the deterministic fake provider.

FakeProvider output is never evidence of model behavior; these tests check sequencing,
budgets, status transitions, parsing, error mapping and the disposition rules.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from refactor_ai import task_format
from refactor_ai.agents import coordinator
from refactor_ai.agents.coordinator import run_workflow, run_workflow_traced
from refactor_ai.contracts import (
    Disposition,
    ProviderError,
    ProviderErrorCode,
    ProviderMode,
    ReferenceCase,
    ReferenceTest,
    ReferenceTestFailure,
    ReferenceTestsResult,
    Role,
    RunnerInfo,
    RunRecord,
    RunStatus,
    WorkflowMode,
    WorkflowOutcome,
    WorkflowRequest,
    WorkflowSettings,
)
from refactor_ai.providers import FakeProvider
from refactor_ai.providers.fake import FAKE_MODEL
from refactor_ai.task_format import REFACTOR_SYSTEM_PROMPT, render_refactor_completion
from refactor_ai.tasks import guard_clauses
from refactor_ai.verification.diffing import changed_lines, unified_diff

SHIP = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight > 0:
        if express:
            return weight * 3
        else:
            return weight * 2
    else:
        raise ValueError("weight must be positive")
'''
GOOD = guard_clauses.to_guard_clauses(SHIP)
WRONG = GOOD.replace("weight <= 0", "weight < 0")
BROKEN = (
    "def shipping_cost(weight, express):\n"
    "    if weight <= 0\n"
    "        raise ValueError('weight must be positive')\n"
    "    return weight * 2\n"
)
FLAT = (
    "def sign(x):\n    if x > 0:\n        return 1\n    elif x < 0:\n"
    "        return -1\n    return 0\n"
)

ANALYSIS_OK = json.dumps(
    {
        "supported_task": True,
        "findings": [
            {
                "type": "nested_conditional",
                "start_line": 3,
                "end_line": 9,
                "reason": "The else branch always raises.",
            }
        ],
        "unsupported_reason": None,
    }
)
ACCEPT = json.dumps(
    {"verdict": "accept", "reasons": ["Same behavior."], "suggested_correction": None}
)
REJECT = json.dumps(
    {
        "verdict": "reject",
        "reasons": ["A weight of 0 no longer raises."],
        "suggested_correction": "Use weight <= 0 in the guard.",
    }
)
UNCERTAIN = json.dumps(
    {"verdict": "uncertain", "reasons": ["Unclear."], "suggested_correction": None}
)

CASE = ReferenceCase(
    case_id="shipping",
    task_type="guard_clauses",
    function_name="shipping_cost",
    original_code=SHIP,
    reference_code=GOOD,
    tests=[
        ReferenceTest(args="[2, True]", expect={"kind": "return", "value": "6"}),
        ReferenceTest(args="[2, False]", expect={"kind": "return", "value": "4"}),
        ReferenceTest(args="[0, True]", expect={"kind": "raise", "exception": "ValueError"}),
    ],
)

ALLOWED_TRANSITIONS = {
    (RunStatus.ANALYZING, RunStatus.GENERATING),
    (RunStatus.ANALYZING, RunStatus.FAILED),
    (RunStatus.GENERATING, RunStatus.VERIFYING),
    (RunStatus.GENERATING, RunStatus.FAILED),
    (RunStatus.VERIFYING, RunStatus.GENERATING),
    (RunStatus.VERIFYING, RunStatus.COMPLETED),
    (RunStatus.VERIFYING, RunStatus.FAILED),
}
OUTCOME_FIELDS = (
    "status",
    "provider_mode",
    "model",
    "analysis",
    "findings",
    "proposed_code",
    "explanation",
    "diff",
    "changed_lines",
    "review",
    "verification",
    "attempts",
    "attempt_count",
    "call_count",
    "stage_timings",
    "stop_reason",
    "error",
    "warnings",
)


def completion(code: str, explanation: str = "Uses guard clauses.") -> str:
    return render_refactor_completion(explanation, code)


def ref_result(status: str, **fields) -> ReferenceTestsResult:
    defaults = {"case_id": CASE.case_id}
    if status in ("pass", "fail"):
        defaults.update(
            total=3, passed=3 if status == "pass" else 2, failed=0 if status == "pass" else 1
        )
        defaults["errored"] = 0
    if status == "fail":
        defaults["failures"] = [
            ReferenceTestFailure(
                index=2,
                kind="missing_exception",
                detail="shipping_cost(0, True) returned 0 (int); expected ValueError.",
            )
        ]
    defaults.update(fields)
    return ReferenceTestsResult(status=status, **defaults)


PASS = ref_result("pass")


class StubRunner:
    """In-memory runner returning fixed results; it never executes anything."""

    def __init__(self, *results):
        self.results = list(results) or [PASS]
        self.calls: list[str] = []

    def info(self) -> RunnerInfo:
        return RunnerInfo(enabled=True)

    def run(self, case, candidate_code):
        self.calls.append(candidate_code)
        result = self.results[min(len(self.calls), len(self.results)) - 1]
        return result(case, candidate_code) if callable(result) else result


@dataclass
class Run:
    outcome: WorkflowOutcome
    trace: coordinator.WorkflowTrace
    statuses: list[RunStatus]
    provider: FakeProvider
    runner: object
    request: WorkflowRequest
    settings: WorkflowSettings

    @property
    def roles(self) -> list[Role]:
        return [request.role for request in self.provider.calls]

    @property
    def reasons(self) -> list[str]:
        return self.outcome.verification.disposition_reasons


DEFAULT = object()


def run(
    code: str = SHIP,
    *,
    script=None,
    mode: str = "multi_role",
    case=DEFAULT,
    runner=DEFAULT,
    provider=None,
    on_status=None,
    **settings,
) -> Run:
    provider = provider or FakeProvider(script=script)
    runner = StubRunner() if runner is DEFAULT else runner
    case = (CASE if code == SHIP else None) if case is DEFAULT else case
    statuses: list[RunStatus] = []

    def record(status):
        statuses.append(status)
        if on_status is not None:
            on_status(status)

    workflow_settings = WorkflowSettings(mode=mode, **settings)
    request = WorkflowRequest(code=code, task_type="guard_clauses", reference_case=case)
    before = request.model_dump()
    outcome, trace = run_workflow_traced(
        request, provider=provider, settings=workflow_settings, runner=runner, on_status=record
    )
    assert request.model_dump() == before, "the request must not be modified"
    result = Run(outcome, trace, statuses, provider, runner, request, workflow_settings)
    check_invariants(result)
    return result


def check_invariants(result: Run) -> None:
    outcome, settings = result.outcome, result.settings
    # The outcome is a valid contract object and can be stored as a run record.
    WorkflowOutcome.model_validate_json(outcome.model_dump_json())
    RunRecord.model_validate(
        {
            "run_id": "a" * 32,
            "created_at": datetime.now(UTC),
            "task_type": "guard_clauses",
            "workflow_mode": settings.mode,
            "original_code": result.request.code,
            "settings": settings,
            **{name: getattr(outcome, name) for name in OUTCOME_FIELDS},
        }
    )
    # Call budgets.
    calls = len(result.provider.calls)
    assert outcome.call_count == calls == len(result.trace.calls)
    assert calls <= (settings.max_calls if settings.mode == WorkflowMode.MULTI_ROLE else 1)
    refactor_calls = result.roles.count(Role.REFACTOR)
    assert refactor_calls <= 1 + settings.max_corrections
    assert outcome.attempt_count == len(outcome.attempts) == refactor_calls
    assert sum(timing.calls for timing in outcome.stage_timings) == calls
    if settings.mode == WorkflowMode.SINGLE_ROLE:
        assert set(result.roles) <= {Role.REFACTOR}
        assert RunStatus.ANALYZING not in result.statuses
    # Status transitions.
    statuses = result.statuses
    assert statuses == result.trace.statuses
    assert statuses[-1] == outcome.status
    assert statuses[0] in (
        RunStatus.ANALYZING,
        RunStatus.GENERATING,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
    )
    for before, after in zip(statuses, statuses[1:], strict=False):
        assert (before, after) in ALLOWED_TRANSITIONS, statuses
    assert (
        sum(
            1
            for before, after in zip(statuses, statuses[1:], strict=False)
            if (before, after) == (RunStatus.VERIFYING, RunStatus.GENERATING)
        )
        <= 1
    )
    # Stop reasons, errors and disposition.
    verification = outcome.verification
    assert verification is not None
    assert outcome.stop_reason in coordinator.STOP_REASONS
    if outcome.status == RunStatus.FAILED:
        assert outcome.error is not None
        assert outcome.stop_reason in coordinator.FAILED_STOP_REASONS
        assert verification.disposition == Disposition.FAILED
        assert outcome.proposed_code is None and outcome.diff is None
    else:
        assert outcome.error is None
        assert outcome.stop_reason in coordinator.COMPLETED_STOP_REASONS
        assert verification.disposition != Disposition.FAILED
        no_change = verification.disposition == Disposition.NO_CHANGE
        assert no_change == (outcome.stop_reason == coordinator.STOP_UNSUPPORTED_INPUT)
        if no_change:
            assert outcome.proposed_code is None and calls == 0
        else:
            assert outcome.proposed_code is not None
            assert outcome.diff == unified_diff(result.request.code, outcome.proposed_code)
            assert outcome.changed_lines == changed_lines(
                result.request.code, outcome.proposed_code
            )
    for reason in verification.disposition_reasons:
        code, separator, text = reason.partition(": ")
        assert separator and code and text, reason
    if verification.disposition == Disposition.PROPOSAL_READY:
        assert verification.syntax.status == "pass"
        assert verification.rubric.status == "pass"
        assert verification.reference_tests.status == "pass"
        assert verification.model_review.status in ("accept", "not_run")
    if result.provider.mode == ProviderMode.FAKE:
        assert coordinator.FAKE_PROVIDER_WARNING in outcome.warnings


# --- Happy paths ----------------------------------------------------------------------


def test_multi_role_happy_path():
    result = run()
    outcome = result.outcome
    assert outcome.status == RunStatus.COMPLETED
    assert outcome.verification.disposition == Disposition.PROPOSAL_READY
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW]
    assert result.statuses == [
        RunStatus.ANALYZING,
        RunStatus.GENERATING,
        RunStatus.VERIFYING,
        RunStatus.COMPLETED,
    ]
    assert outcome.stop_reason == coordinator.STOP_NO_CORRECTION_NEEDED
    assert outcome.proposed_code == GOOD
    assert outcome.explanation.startswith("FAKE PROVIDER")
    assert outcome.analysis.source == "model" and outcome.findings == outcome.analysis.findings
    assert outcome.review.verdict.value == "accept"
    assert outcome.model == FAKE_MODEL
    assert outcome.provider_mode == ProviderMode.FAKE
    assert [(t.stage, t.attempt, t.calls) for t in outcome.stage_timings] == [
        ("validation", 0, 0),
        ("analysis", 0, 1),
        ("generation", 0, 1),
        ("verification", 0, 0),
        ("review", 0, 1),
    ]
    assert result.runner.calls == [GOOD]
    assert [call.prompt_version for call in result.trace.calls] == [
        "analysis-v1",
        task_format.PROMPT_VERSION,
        "review-v1",
    ]
    assert result.trace.prompt_versions["refactor"] == task_format.PROMPT_VERSION
    assert all(call.model == FAKE_MODEL for call in result.trace.calls)
    assert outcome.verification.disposition_reasons[0].startswith("ready: ")


def test_single_role_happy_path():
    result = run(mode="single_role")
    outcome = result.outcome
    assert result.roles == [Role.REFACTOR]
    assert result.statuses == [RunStatus.GENERATING, RunStatus.VERIFYING, RunStatus.COMPLETED]
    assert outcome.verification.disposition == Disposition.PROPOSAL_READY
    assert outcome.verification.model_review.status == "not_run"
    assert outcome.analysis is None and outcome.findings == [] and outcome.review is None
    assert outcome.stop_reason == coordinator.STOP_SINGLE_ROLE_COMPLETE
    prompt = result.provider.calls[0].messages
    assert prompt[0].content == REFACTOR_SYSTEM_PROMPT
    assert "Analysis notes:" not in prompt[-1].content


def test_single_role_never_corrects_even_when_rejected():
    result = run(mode="single_role", script={Role.REFACTOR: [completion(SHIP)]})
    assert result.outcome.verification.disposition == Disposition.REJECTED
    assert result.roles == [Role.REFACTOR]


def test_run_workflow_returns_the_traced_outcome():
    request = WorkflowRequest(code=SHIP, task_type="guard_clauses", reference_case=CASE)
    first = run_workflow(
        request, provider=FakeProvider(), settings=WorkflowSettings(), runner=StubRunner()
    )
    second, _ = run_workflow_traced(
        request, provider=FakeProvider(), settings=WorkflowSettings(), runner=StubRunner()
    )
    ignore = {"stage_timings", "attempts"}
    assert first.model_dump(exclude=ignore) == second.model_dump(exclude=ignore)


def test_multi_role_passes_analysis_findings_as_notes():
    result = run(script={Role.ANALYSIS: [ANALYSIS_OK]})
    refactor_prompt = result.provider.calls[1].messages[-1].content
    assert "Analysis notes:\n- lines 3-9: The else branch always raises." in refactor_prompt


def test_adapter_is_requested_for_the_refactoring_role_only():
    result = run(refactor_use_adapter=True)
    flags = [(request.role, request.use_adapter) for request in result.provider.calls]
    assert flags == [(Role.ANALYSIS, False), (Role.REFACTOR, True), (Role.REVIEW, False)]
    assert result.outcome.model.use_adapter is True
    assert result.outcome.attempts[0].model.use_adapter is True


def test_single_role_adapter_flag():
    result = run(mode="single_role", refactor_use_adapter=True)
    assert result.provider.calls[0].use_adapter is True


def test_generation_settings_are_applied_per_role():
    result = run()
    budgets = {request.role: request.config.max_new_tokens for request in result.provider.calls}
    settings = result.settings.generation
    assert budgets == {role: settings[role].max_new_tokens for role in settings}
    for request in result.provider.calls:
        assert request.config.timeout_s <= settings[request.role].timeout_s


# --- Unsupported input ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("def shipping_cost(:\n    pass\n", "syntax_error"),
        ("x = 1\n", "not_single_function"),
        ("def f(x):\n    print(x)\n    return x\n", "denied_call:print"),
        ("async def f(x):\n    return x\n", "async_function"),
        ("@cache\ndef f(x):\n    return x\n", "decorated_function"),
        (FLAT, "no_opportunity"),
        ("def f(x):\n" + "    x = x + 1\n" * 70 + "    return x\n", "too_long"),
    ],
)
@pytest.mark.parametrize("mode", ["multi_role", "single_role"])
def test_unsupported_input_completes_without_calls(code, reason, mode):
    result = run(code, mode=mode, case=None)
    outcome = result.outcome
    assert result.provider.calls == []
    assert result.statuses == [RunStatus.COMPLETED]
    assert outcome.status == RunStatus.COMPLETED
    assert outcome.verification.disposition == Disposition.NO_CHANGE
    assert outcome.stop_reason == coordinator.STOP_UNSUPPORTED_INPUT
    assert outcome.call_count == 0 and outcome.attempt_count == 0
    assert outcome.analysis.source == "static" and outcome.analysis.supported_task is False
    assert outcome.analysis.unsupported_reason
    codes = [item.partition(": ")[0] for item in result.reasons]
    assert reason in codes
    text = dict(item.split(": ", 1) for item in result.reasons)[reason]
    assert text == guard_clauses.reason_text(reason)
    assert outcome.verification.reference_tests.status == "not_run"
    assert outcome.verification.syntax.status == "not_run"


@pytest.mark.parametrize("mode", ["multi_role", "single_role"])
def test_expression_too_deep_for_the_rewrite_completes_as_no_change(mode):
    # Valid Python inside the size limits whose a + b + ... chain is nested deeper than
    # the recursion limit of the ast helpers that check_input uses for the rewrite.
    chain = "+".join(["x"] * 1000)
    code = (
        f"def f(x):\n    if x:\n        return {chain}\n    else:\n"
        "        if x > 1:\n            return 1\n        return 2\n"
    )
    assert len(code) <= guard_clauses.MAX_INPUT_CHARS
    result = run(code, mode=mode, case=None)
    outcome = result.outcome
    assert outcome.error is None and outcome.status == RunStatus.COMPLETED
    assert outcome.verification.disposition == Disposition.NO_CHANGE
    assert outcome.stop_reason == coordinator.STOP_UNSUPPORTED_INPUT
    assert result.provider.calls == [] and result.reasons


def test_unsupported_task_type_is_no_change():
    provider = FakeProvider()
    request = WorkflowRequest(code=SHIP, task_type="extract_method")
    outcome = run_workflow(request, provider=provider, settings=WorkflowSettings())
    assert provider.calls == []
    assert outcome.verification.disposition == Disposition.NO_CHANGE
    assert outcome.verification.disposition_reasons == [
        "unsupported_task_type: Only the guard_clauses task is supported."
    ]


def test_reference_case_mismatch_fails_before_any_call():
    other = CASE.model_copy(update={"original_code": GOOD})
    result = run(case=other)
    assert result.provider.calls == []
    assert result.outcome.status == RunStatus.FAILED
    assert result.outcome.error.code == "reference_case_mismatch"
    assert result.outcome.error.stage == "validation"
    assert result.statuses == [RunStatus.FAILED]


def test_reference_case_line_endings_are_normalized():
    crlf = SHIP.replace("\n", "\r\n").rstrip() + "\r\n\r\n"
    result = run(crlf, case=CASE)
    assert result.outcome.verification.disposition == Disposition.PROPOSAL_READY


@pytest.mark.parametrize("max_calls", [1, 2])
def test_multi_role_needs_three_calls(max_calls):
    result = run(max_calls=max_calls)
    assert result.provider.calls == []
    assert result.outcome.error.code == "invalid_settings"
    assert result.outcome.stop_reason == coordinator.STOP_INVALID_SETTINGS


def test_single_role_runs_with_one_call_budget():
    result = run(mode="single_role", max_calls=1)
    assert result.outcome.verification.disposition == Disposition.PROPOSAL_READY


# --- Analysis output ------------------------------------------------------------------


def test_fenced_analysis_json_is_repaired():
    result = run(script={Role.ANALYSIS: [f"```json\n{ANALYSIS_OK}\n```"]})
    assert result.outcome.analysis.source == "model"
    assert result.outcome.findings[0].reason == "The else branch always raises."
    assert any("repaired (code_fence_removed)" in item for item in result.outcome.warnings)
    assert result.trace.calls[0].parse_repaired is True


@pytest.mark.parametrize(
    ("output", "problem"),
    [
        ("not json at all", "could not be parsed"),
        ('{"supported_task": true, "findings": [', "could not be parsed"),
        ('{"supported_task": "yes", "findings": []}', "could not be parsed"),
        ('{"supported_task": true, "findings": [], "notes": "x"}', "could not be parsed"),
        ('{"supported_task": true, "findings": []}', "no valid finding"),
        ('{"supported_task": false, "findings": []}', "unsupported"),
    ],
)
def test_unusable_analysis_falls_back_to_static_findings(output, problem):
    result = run(script={Role.ANALYSIS: [output]})
    outcome = result.outcome
    static = guard_clauses.check_input(SHIP).opportunities
    assert outcome.analysis.source == "static"
    assert [(f.start_line, f.end_line) for f in outcome.findings] == [
        (item.start_line, item.end_line) for item in static
    ]
    assert any(problem in item and "source=static" in item for item in outcome.warnings)
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW]
    assert outcome.verification.disposition == Disposition.PROPOSAL_READY


def test_findings_outside_the_input_are_dropped_with_warnings():
    output = json.dumps(
        {
            "supported_task": True,
            "findings": [
                {"type": "nested_conditional", "start_line": 3, "end_line": 9, "reason": "ok"},
                {"type": "nested_conditional", "start_line": 40, "end_line": 45, "reason": "x"},
                {"type": "nested_if", "start_line": 3, "end_line": 4, "reason": "x"},
                {"type": "nested_conditional", "start_line": 5, "end_line": 4, "reason": "x"},
            ],
            "unsupported_reason": None,
        }
    )
    result = run(script={Role.ANALYSIS: [output]})
    assert result.outcome.analysis.source == "model"
    assert [(f.start_line, f.end_line) for f in result.outcome.findings] == [(3, 9)]
    dropped = [item for item in result.outcome.warnings if "the finding was dropped" in item]
    assert len(dropped) == 3
    assert any("outside the input (1-9)" in item for item in dropped)


def test_all_findings_invalid_falls_back_to_static():
    output = json.dumps(
        {
            "supported_task": True,
            "findings": [
                {"type": "nested_conditional", "start_line": 0, "end_line": 2, "reason": "x"}
            ],
            "unsupported_reason": None,
        }
    )
    result = run(script={Role.ANALYSIS: [output]})
    assert result.outcome.analysis.source == "static"


# --- Refactoring output ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("output", "error"),
    [
        ("", "empty_output"),
        ("I cannot help with that.", "no_code_block"),
        ("Explanation: x\n```python\ndef shipping_cost(weight, express):\n    if", "unterminated"),
    ],
)
def test_single_role_unparseable_output_fails(output, error):
    result = run(mode="single_role", script={Role.REFACTOR: [output]})
    outcome = result.outcome
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == "unparseable_output" and outcome.error.stage == "generation"
    assert outcome.stop_reason == coordinator.STOP_UNPARSEABLE_OUTPUT
    assert result.statuses == [RunStatus.GENERATING, RunStatus.VERIFYING, RunStatus.FAILED]
    assert outcome.attempts[0].parse_error.startswith(error)
    assert outcome.attempts[0].raw_output == output
    assert result.runner.calls == []


def test_multi_role_corrects_an_unparseable_first_answer():
    result = run(script={Role.REFACTOR: ["I cannot help.", completion(GOOD)]})
    outcome = result.outcome
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REFACTOR, Role.REVIEW]
    assert result.statuses == [
        RunStatus.ANALYZING,
        RunStatus.GENERATING,
        RunStatus.VERIFYING,
        RunStatus.GENERATING,
        RunStatus.VERIFYING,
        RunStatus.COMPLETED,
    ]
    assert outcome.stop_reason == coordinator.STOP_CORRECTION_USED
    assert outcome.verification.disposition == Disposition.PROPOSAL_READY
    assert outcome.attempts[0].parse_error == "no_code_block"
    assert outcome.attempts[0].verification.disposition == Disposition.FAILED
    correction = result.provider.calls[2].messages[-1].content
    assert "no fenced Python code block was found" in correction
    assert "Previous answer:" not in correction
    assert result.trace.calls[2].prompt_version == "correction-v2"


def test_multi_role_fails_when_both_answers_are_unparseable():
    result = run(script={Role.REFACTOR: ["", "still nothing"]})
    outcome = result.outcome
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REFACTOR]
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == "unparseable_output"
    assert outcome.attempt_count == 2


def test_unparseable_correction_keeps_the_first_proposal():
    result = run(
        script={Role.REFACTOR: [completion(GOOD), "no code"], Role.REVIEW: [REJECT]},
    )
    outcome = result.outcome
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW, Role.REFACTOR]
    assert outcome.status == RunStatus.COMPLETED
    assert outcome.proposed_code == GOOD
    assert outcome.verification.disposition == Disposition.REJECTED
    assert outcome.verification == outcome.attempts[0].verification
    assert any("first proposal" in item for item in outcome.warnings)


def test_repaired_refactor_output_is_marked():
    unfenced = "Explanation: guard first\n" + GOOD
    result = run(mode="single_role", script={Role.REFACTOR: [unfenced]})
    attempt = result.outcome.attempts[0]
    assert attempt.parse_repaired is True and attempt.proposed_code == GOOD
    assert any("repaired (unfenced_code)" in item for item in result.outcome.warnings)


def test_model_supplied_diff_is_ignored():
    output = (
        f"Explanation: done\n```diff\n-    if weight > 0:\n+    return 0\n```\n```python\n{GOOD}```"
    )
    result = run(mode="single_role", script={Role.REFACTOR: [output]})
    assert result.outcome.proposed_code == GOOD
    assert result.outcome.diff == unified_diff(SHIP, GOOD)


# --- Deterministic checks and correction -----------------------------------------------


def test_syntax_invalid_candidate_is_rejected_in_single_role():
    result = run(mode="single_role", script={Role.REFACTOR: [completion(BROKEN)]})
    verification = result.outcome.verification
    assert verification.disposition == Disposition.REJECTED
    assert verification.syntax.status == "fail" and "line 2" in verification.syntax.error
    assert verification.rubric.status == "not_run"
    assert verification.reference_tests.status == "not_run"
    assert result.runner.calls == []
    assert result.reasons[0].startswith("syntax_fail: ")


def test_syntax_invalid_candidate_is_corrected_in_multi_role():
    result = run(script={Role.REFACTOR: [completion(BROKEN), completion(GOOD)]})
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW, Role.REFACTOR, Role.REVIEW]
    assert result.outcome.verification.disposition == Disposition.PROPOSAL_READY
    correction = result.provider.calls[3].messages[-1].content
    assert "The code is not valid Python" in correction
    assert "Previous answer:\n```python\n" + BROKEN.rstrip() in correction


def test_rubric_failure_is_rejected_and_reported():
    result = run(mode="single_role", script={Role.REFACTOR: [completion(SHIP)]})
    verification = result.outcome.verification
    assert verification.rubric.status == "fail"
    assert verification.rubric.checks["nesting_reduced"] is False
    assert any("Nesting depth did not decrease" in text for text in verification.rubric.reasons)
    assert verification.disposition == Disposition.REJECTED
    assert result.outcome.diff == ""


def test_candidate_outside_task_constraints_is_never_executed():
    # Candidate text only: the workflow must refuse to hand it to any runner.
    candidate = GOOD.replace("return weight * 2", "return eval('weight * 2')")
    result = run(mode="single_role", script={Role.REFACTOR: [completion(candidate)]})
    verification = result.outcome.verification
    assert verification.reference_tests.status == "not_run"
    assert result.runner.calls == []
    assert verification.disposition == Disposition.REJECTED


@pytest.mark.parametrize(
    ("tests", "disposition", "code"),
    [
        (PASS, Disposition.PROPOSAL_READY, "ready"),
        (ref_result("fail"), Disposition.REJECTED, "tests_fail"),
        (ref_result("error", reason="runner crashed"), Disposition.REJECTED, "tests_error"),
        (ref_result("not_run", reason="disabled"), Disposition.UNCERTAIN, "tests_not_run"),
        (
            ref_result("not_available", reason="no tests"),
            Disposition.UNCERTAIN,
            "tests_not_available",
        ),
        (ref_result("pass", total=0, passed=0), Disposition.UNCERTAIN, "tests_not_available"),
    ],
)
def test_reference_test_status_drives_disposition(tests, disposition, code):
    result = run(mode="single_role", runner=StubRunner(tests))
    assert result.outcome.verification.reference_tests == tests
    assert result.outcome.verification.disposition == disposition
    assert result.reasons[0].startswith(f"{code}: ")


def test_missing_reference_case_is_not_available_and_uncertain():
    result = run(case=None)
    verification = result.outcome.verification
    assert verification.reference_tests.status == "not_available"
    assert verification.disposition == Disposition.UNCERTAIN
    assert result.runner.calls == []


def test_missing_runner_is_not_run_and_uncertain():
    result = run(runner=None)
    verification = result.outcome.verification
    assert verification.reference_tests.status == "not_run"
    assert verification.disposition == Disposition.UNCERTAIN


def test_failed_tests_trigger_one_correction_with_test_feedback():
    runner = StubRunner(ref_result("fail"), PASS)
    result = run(script={Role.REFACTOR: [completion(WRONG), completion(GOOD)]}, runner=runner)
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW, Role.REFACTOR, Role.REVIEW]
    assert runner.calls == [WRONG, GOOD]
    assert result.outcome.verification.disposition == Disposition.PROPOSAL_READY
    assert result.outcome.attempts[0].verification.disposition == Disposition.REJECTED
    correction = result.provider.calls[3].messages[-1].content
    assert "Reference tests: 2 of 3 passed." in correction
    assert "Test 2 (missing_exception)" in correction
    review_prompt = result.provider.calls[2].messages[-1].content
    assert "- reference tests: fail (2 of 3 passed)" in review_prompt


def test_model_accept_never_overrides_failed_tests():
    runner = StubRunner(ref_result("fail"))
    result = run(script={Role.REVIEW: [ACCEPT, ACCEPT]}, runner=runner)
    verification = result.outcome.verification
    assert verification.model_review.status == "accept"
    assert verification.disposition == Disposition.REJECTED
    assert result.outcome.stop_reason == coordinator.STOP_CORRECTION_USED


# --- Review ---------------------------------------------------------------------------


def test_review_reject_triggers_correction_then_accept():
    result = run(
        script={Role.REFACTOR: [completion(WRONG), completion(GOOD)], Role.REVIEW: [REJECT, ACCEPT]}
    )
    outcome = result.outcome
    assert outcome.call_count == 5 and outcome.attempt_count == 2
    assert outcome.verification.disposition == Disposition.PROPOSAL_READY
    assert outcome.attempts[0].review.verdict.value == "reject"
    assert outcome.review.verdict.value == "accept"
    correction = result.provider.calls[3].messages[-1].content
    assert "The reviewer rejected the proposal: A weight of 0 no longer raises." in correction
    assert "Reviewer suggestion: Use weight <= 0 in the guard." in correction


def test_fenced_reject_with_a_code_block_in_its_suggestion_triggers_correction():
    suggestion = "```python\nif weight <= 0:\n    raise ValueError('weight must be positive')\n```"
    reject = json.dumps(
        {
            "verdict": "reject",
            "reasons": ["A weight of 0 no longer raises."],
            "suggested_correction": suggestion,
        }
    )
    result = run(
        script={
            Role.REFACTOR: [completion(WRONG), completion(GOOD)],
            Role.REVIEW: [f"```json\n{reject}\n```", ACCEPT],
        }
    )
    first = result.outcome.attempts[0]
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW, Role.REFACTOR, Role.REVIEW]
    assert first.verification.model_review.status == "reject"
    assert first.review.suggested_correction == suggestion
    assert result.trace.calls[2].parse_repairs == ["code_fence_removed"]
    assert result.outcome.stop_reason == coordinator.STOP_CORRECTION_USED
    correction = result.provider.calls[3].messages[-1].content
    assert "The reviewer rejected the proposal: A weight of 0 no longer raises." in correction
    assert "Reviewer suggestion: ```python" in correction


def test_analysis_json_followed_by_a_code_block_is_used():
    output = f"{ANALYSIS_OK}\n```\ndef shipping_cost(weight, express):\n    return 0\n```"
    result = run(script={Role.ANALYSIS: [output]})
    assert result.outcome.analysis.source == "model"
    assert result.trace.calls[0].parse_repairs == ["json_object_extracted"]


def test_correction_exhaustion_stops_after_five_calls():
    result = run(
        script={
            Role.REFACTOR: [completion(WRONG), completion(WRONG)],
            Role.REVIEW: [REJECT, REJECT],
        }
    )
    outcome = result.outcome
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW, Role.REFACTOR, Role.REVIEW]
    assert outcome.verification.disposition == Disposition.REJECTED
    assert outcome.stop_reason == coordinator.STOP_CORRECTION_USED
    assert outcome.attempt_count == 2
    assert result.statuses.count(RunStatus.GENERATING) == 2


def test_uncertain_review_is_uncertain_without_correction():
    result = run(script={Role.REVIEW: [UNCERTAIN]})
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW]
    assert result.outcome.verification.disposition == Disposition.UNCERTAIN
    assert result.outcome.stop_reason == coordinator.STOP_NO_CORRECTION_NEEDED
    assert result.reasons == ["review_uncertain: The model review was uncertain."]


@pytest.mark.parametrize(
    "output",
    ["", "looks fine", '{"verdict": "maybe"}', '{"verdict": "accept", "confidence": 0.9}'],
)
def test_malformed_review_is_an_error_and_uncertain(output):
    result = run(script={Role.REVIEW: [output]})
    verification = result.outcome.verification
    assert verification.model_review.status == "error"
    assert verification.model_review.error.startswith("The review output could not be parsed")
    assert verification.disposition == Disposition.UNCERTAIN
    assert result.outcome.review is None
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW]
    assert any("the review is recorded as an error" in item for item in result.outcome.warnings)


def test_review_verdict_case_is_normalized():
    output = '```json\n{"verdict": "ACCEPT", "reasons": ["ok"], "suggested_correction": null}\n```'
    result = run(script={Role.REVIEW: [output]})
    assert result.outcome.verification.model_review.status == "accept"
    assert result.trace.calls[2].parse_repairs == ["code_fence_removed", "verdict_case_normalized"]


def test_review_prompt_contains_original_candidate_and_checks():
    result = run(script={Role.REFACTOR: [completion(WRONG)]}, runner=StubRunner(PASS))
    prompt = result.provider.calls[2].messages[-1].content
    assert "Code:\n```python\n" + SHIP.rstrip() + "\n```" in prompt
    assert "Proposed refactoring:\n```python\n" + WRONG.rstrip() in prompt
    assert "- syntax: pass" in prompt and "- rubric: pass" in prompt
    assert prompt.index("Code:") < prompt.index("Proposed refactoring:")


def test_correction_disabled():
    result = run(script={Role.REVIEW: [REJECT]}, max_corrections=0)
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW]
    assert result.outcome.stop_reason == coordinator.STOP_CORRECTION_DISABLED
    assert result.outcome.verification.disposition == Disposition.REJECTED
    assert any("max_corrections is 0" in item for item in result.outcome.warnings)


@pytest.mark.parametrize("max_calls", [3, 4])
def test_correction_needs_two_remaining_calls(max_calls):
    result = run(script={Role.REVIEW: [REJECT]}, max_calls=max_calls)
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW]
    assert result.outcome.stop_reason == coordinator.STOP_CALL_BUDGET_EXHAUSTED
    assert result.outcome.verification.disposition == Disposition.REJECTED


def too_long(tokens: int = 2391) -> ProviderError:
    return ProviderError(
        code=ProviderErrorCode.INPUT_TOO_LONG,
        message=f"The prompt has {tokens} tokens; max_input_tokens is 2048.",
    )


def test_oversized_correction_prompt_skips_the_correction():
    result = run(
        script={Role.REFACTOR: [completion(WRONG), too_long()], Role.REVIEW: [REJECT]},
    )
    outcome = result.outcome
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW, Role.REFACTOR]
    assert result.statuses == [
        RunStatus.ANALYZING,
        RunStatus.GENERATING,
        RunStatus.VERIFYING,
        RunStatus.GENERATING,
        RunStatus.VERIFYING,
        RunStatus.COMPLETED,
    ]
    assert outcome.status == RunStatus.COMPLETED and outcome.error is None
    assert outcome.stop_reason == coordinator.STOP_CORRECTION_INPUT_TOO_LONG
    assert outcome.proposed_code == WRONG
    assert outcome.verification == outcome.attempts[0].verification
    assert outcome.verification.disposition == Disposition.REJECTED
    assert outcome.attempt_count == 2 and outcome.attempts[1].proposed_code is None
    assert result.trace.calls[3].error.code == ProviderErrorCode.INPUT_TOO_LONG
    skipped = [item for item in outcome.warnings if "correction was skipped" in item]
    assert len(skipped) == 1 and "2391 tokens" in skipped[0]
    assert not any("produced no parseable code" in item for item in outcome.warnings)


def test_oversized_correction_after_an_unparseable_answer_fails_as_unparseable():
    result = run(script={Role.REFACTOR: ["I cannot help.", too_long()]})
    outcome = result.outcome
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR, Role.REFACTOR]
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == "unparseable_output"
    assert "no fenced Python code block was found" in outcome.error.message
    assert any("correction was skipped" in item for item in outcome.warnings)


@pytest.mark.parametrize(
    ("script", "stage"),
    [
        ({Role.ANALYSIS: [too_long()]}, "analysis"),
        ({Role.REFACTOR: [too_long()]}, "generation"),
        ({Role.REVIEW: [too_long(4200)]}, "review"),
        (
            {
                Role.REFACTOR: [completion(WRONG), completion(GOOD)],
                Role.REVIEW: [REJECT, too_long()],
            },
            "review",
        ),
    ],
)
def test_input_too_long_outside_the_correction_fails_the_run(script, stage):
    result = run(script=script)
    outcome = result.outcome
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == "input_too_long" and outcome.error.stage == stage
    assert outcome.stop_reason == coordinator.STOP_PROVIDER_ERROR


def test_single_role_input_too_long_fails_the_run():
    result = run(mode="single_role", script={Role.REFACTOR: [too_long()]})
    assert result.outcome.error.code == "input_too_long"
    assert result.outcome.stop_reason == coordinator.STOP_PROVIDER_ERROR


def test_unparseable_first_answer_without_correction_budget_fails():
    result = run(script={Role.REFACTOR: [""]}, max_calls=3)
    assert result.roles == [Role.ANALYSIS, Role.REFACTOR]
    assert result.outcome.error.code == "unparseable_output"


# --- Provider errors, deadlines and internal errors -----------------------------------


def error(code: ProviderErrorCode, message: str = "provider problem") -> ProviderError:
    return ProviderError(code=code, message=message)


@pytest.mark.parametrize("code", list(ProviderErrorCode))
def test_provider_error_codes_are_mapped(code):
    result = run(script={Role.REFACTOR: [error(code)]})
    outcome = result.outcome
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == code.value
    assert outcome.error.message == "provider problem"
    assert outcome.error.stage == "generation"
    assert outcome.stop_reason == coordinator.STOP_PROVIDER_ERROR
    assert result.reasons == [f"{code.value}: provider problem"]


@pytest.mark.parametrize(
    ("mode", "script", "stage", "roles", "statuses"),
    [
        (
            "multi_role",
            {Role.ANALYSIS: [error(ProviderErrorCode.TIMEOUT)]},
            "analysis",
            [Role.ANALYSIS],
            [RunStatus.ANALYZING, RunStatus.FAILED],
        ),
        (
            "multi_role",
            {Role.REFACTOR: [error(ProviderErrorCode.TIMEOUT)]},
            "generation",
            [Role.ANALYSIS, Role.REFACTOR],
            [RunStatus.ANALYZING, RunStatus.GENERATING, RunStatus.FAILED],
        ),
        (
            "multi_role",
            {Role.REVIEW: [error(ProviderErrorCode.TIMEOUT)]},
            "review",
            [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW],
            [RunStatus.ANALYZING, RunStatus.GENERATING, RunStatus.VERIFYING, RunStatus.FAILED],
        ),
        (
            "multi_role",
            {
                Role.REFACTOR: [completion(WRONG), error(ProviderErrorCode.TIMEOUT)],
                Role.REVIEW: [REJECT],
            },
            "generation",
            [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW, Role.REFACTOR],
            [
                RunStatus.ANALYZING,
                RunStatus.GENERATING,
                RunStatus.VERIFYING,
                RunStatus.GENERATING,
                RunStatus.FAILED,
            ],
        ),
        (
            "multi_role",
            {
                Role.REFACTOR: [completion(WRONG), completion(GOOD)],
                Role.REVIEW: [REJECT, error(ProviderErrorCode.TIMEOUT)],
            },
            "review",
            [Role.ANALYSIS, Role.REFACTOR, Role.REVIEW, Role.REFACTOR, Role.REVIEW],
            [
                RunStatus.ANALYZING,
                RunStatus.GENERATING,
                RunStatus.VERIFYING,
                RunStatus.GENERATING,
                RunStatus.VERIFYING,
                RunStatus.FAILED,
            ],
        ),
        (
            "single_role",
            {Role.REFACTOR: [error(ProviderErrorCode.TIMEOUT)]},
            "generation",
            [Role.REFACTOR],
            [RunStatus.GENERATING, RunStatus.FAILED],
        ),
    ],
)
def test_provider_timeout_in_each_role_fails_the_run(mode, script, stage, roles, statuses):
    result = run(mode=mode, script=script)
    outcome = result.outcome
    assert result.roles == roles
    assert result.statuses == statuses
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == "timeout" and outcome.error.stage == stage
    assert outcome.verification.disposition == Disposition.FAILED
    assert outcome.proposed_code is None
    if stage == "review":
        assert outcome.verification.model_review.status == "error"
        assert outcome.verification.syntax.status == "pass"
        assert outcome.attempts[-1].verification == outcome.verification
    else:
        assert outcome.verification.model_review.status == "not_run"


def test_failed_generation_call_is_recorded_as_an_attempt():
    result = run(mode="single_role", script={Role.REFACTOR: [error(ProviderErrorCode.BUSY)]})
    attempt = result.outcome.attempts[0]
    assert attempt.proposed_code is None and attempt.parse_error is None
    assert result.trace.calls[0].error.code == ProviderErrorCode.BUSY


def test_provider_tracebacks_are_not_shown_to_users():
    message = 'Traceback (most recent call last):\n  File "/home/me/secret.py", line 1'
    result = run(script={Role.ANALYSIS: [error(ProviderErrorCode.GENERATION_ERROR, message)]})
    assert result.outcome.error.message == "The provider reported an internal error."
    assert "secret" not in result.outcome.model_dump_json()


class RaisingProvider(FakeProvider):
    def generate(self, request):
        self.calls.append(request)
        raise RuntimeError("internal detail C:\\Users\\someone\\secret")


def test_unexpected_exception_becomes_internal_error():
    result = run(provider=RaisingProvider())
    outcome = result.outcome
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == "internal_error" and outcome.error.stage == "analysis"
    assert outcome.error.message == coordinator.INTERNAL_ERROR_MESSAGE
    assert "secret" not in outcome.model_dump_json()
    assert outcome.call_count == 1


def test_internal_error_while_assembling_the_failure_still_returns(monkeypatch):
    def broken(self, failure):
        raise RuntimeError("cannot build")

    monkeypatch.setattr(coordinator._Workflow, "_failed", broken)
    statuses = []
    outcome, trace = run_workflow_traced(
        WorkflowRequest(code=SHIP, task_type="guard_clauses"),
        provider=RaisingProvider(),
        settings=WorkflowSettings(),
        on_status=statuses.append,
    )
    assert outcome.status == RunStatus.FAILED and outcome.error.code == "internal_error"
    assert outcome.verification.disposition == Disposition.FAILED
    assert outcome.call_count == 1 and statuses == [RunStatus.ANALYZING, RunStatus.FAILED]
    WorkflowOutcome.model_validate_json(outcome.model_dump_json())


class AdapterIgnoringProvider(FakeProvider):
    def generate(self, request):
        result = super().generate(request)
        return result.model_copy(
            update={"model": result.model.model_copy(update={"use_adapter": False})}
        )


def test_adapter_silently_not_applied_fails_the_run():
    result = run(provider=AdapterIgnoringProvider(), refactor_use_adapter=True)
    outcome = result.outcome
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == "model_load_error" and outcome.error.stage == "generation"


class LengthProvider(FakeProvider):
    def generate(self, request):
        return super().generate(request).model_copy(update={"finish_reason": "length"})


def test_token_limit_finish_is_warned():
    result = run(mode="single_role", provider=LengthProvider())
    assert any("reached the token limit" in item for item in result.outcome.warnings)


def slow(text: str, seconds: float):
    def respond(request):
        time.sleep(seconds)
        return text

    return respond


def test_run_deadline_caps_the_call_timeout():
    result = run(provider=FakeProvider(delay_s=0.3), run_timeout_s=0.2)
    outcome = result.outcome
    assert outcome.status == RunStatus.FAILED
    assert outcome.error.code == "run_timeout" and outcome.error.stage == "analysis"
    assert outcome.stop_reason == coordinator.STOP_RUN_TIMEOUT
    assert all(request.config.timeout_s <= 0.2 for request in result.provider.calls)


def test_run_deadline_is_checked_before_the_next_call():
    result = run(script={Role.ANALYSIS: [slow(ANALYSIS_OK, 0.4)]}, run_timeout_s=0.2)
    outcome = result.outcome
    assert result.roles == [Role.ANALYSIS]
    assert outcome.error.code == "run_timeout" and outcome.error.stage == "generation"
    assert result.statuses == [RunStatus.ANALYZING, RunStatus.FAILED]
    assert "0.2 s time limit before the generation step" in outcome.error.message


def test_run_deadline_is_checked_before_verification():
    result = run(
        mode="single_role",
        script={Role.REFACTOR: [slow(completion(GOOD), 0.4)]},
        run_timeout_s=0.2,
    )
    outcome = result.outcome
    assert outcome.error.code == "run_timeout" and outcome.error.stage == "verification"
    assert outcome.verification.reference_tests.status == "not_run"
    assert result.runner.calls == []
    assert outcome.attempts[0].proposed_code == GOOD
    assert outcome.attempts[0].verification == outcome.verification


def test_call_timeouts_never_exceed_the_remaining_run_time():
    result = run(run_timeout_s=30.0)
    timeouts = [request.config.timeout_s for request in result.provider.calls]
    assert all(value <= 30.0 for value in timeouts)
    assert timeouts == sorted(timeouts, reverse=True)


# --- Status callback, warnings and the original code -----------------------------------


def test_failing_status_callback_does_not_stop_the_run():
    def explode(status):
        raise RuntimeError("storage unavailable")

    result = run(on_status=explode)
    assert result.outcome.verification.disposition == Disposition.PROPOSAL_READY
    assert any("status callback failed" in item for item in result.outcome.warnings)


def test_markdown_fence_in_input_is_warned():
    code = SHIP.replace('"""Return the shipping cost."""', '"""Return the cost, see ```docs```."""')
    result = run(code, case=None)
    assert any("Markdown fence" in item for item in result.outcome.warnings)


def test_original_code_is_kept_verbatim():
    code = SHIP.replace("\n", "\r\n")
    result = run(code, case=None)
    assert result.request.code == code
    assert result.outcome.diff == unified_diff(code, GOOD)
    assert result.outcome.changed_lines == [3, 4, 5, 6, 7]
    assert "\r" not in result.outcome.diff


def test_fake_provider_warning_is_present():
    result = run(mode="single_role")
    assert result.outcome.warnings[0] == coordinator.FAKE_PROVIDER_WARNING


# --- Integration with the real runner ------------------------------------------------


@pytest.fixture(scope="module")
def real_runner(tmp_path_factory):
    if sys.platform not in ("win32", "linux"):
        pytest.skip("The reference runner supports Windows and Linux only")
    from refactor_ai.verification.runner import RunnerLimits, SubprocessReferenceRunner

    runner = SubprocessReferenceRunner(
        RunnerLimits(wall_timeout_s=20.0), work_root=tmp_path_factory.mktemp("workflow-runner")
    )
    info = runner.info()
    assert info.enabled, info.reason
    return runner


def test_real_runner_proposal_ready(real_runner):
    result = run(runner=real_runner)
    verification = result.outcome.verification
    assert verification.reference_tests.status == "pass"
    assert verification.reference_tests.passed == 3
    assert verification.disposition == Disposition.PROPOSAL_READY


def test_real_runner_failure_drives_the_correction(real_runner):
    result = run(script={Role.REFACTOR: [completion(WRONG), completion(GOOD)]}, runner=real_runner)
    first = result.outcome.attempts[0].verification
    assert first.reference_tests.status == "fail"
    assert first.reference_tests.failures[0].kind == "missing_exception"
    assert result.outcome.verification.disposition == Disposition.PROPOSAL_READY
    correction = result.provider.calls[3].messages[-1].content
    assert "expected ValueError to be raised" in correction

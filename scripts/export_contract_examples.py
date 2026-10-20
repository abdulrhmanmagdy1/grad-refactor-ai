"""Write the contract example JSON files under docs/architecture/examples/.

Each example is built from the Pydantic models in refactor_ai.contracts and from the
service's own record and error helpers, validated, and written with a fixed layout, so
the output is deterministic. tests/test_contract_examples.py fails when a file is
missing, stale, unexpected or invalid.

    python -m uv run python scripts/export_contract_examples.py          # write files
    python -m uv run python scripts/export_contract_examples.py --check  # verify only

The examples illustrate the schema; they are not results. Run records use the labelled
fake provider; the local-model identity, reference cases, timings and token counts are
placeholders. Free-form values chosen by other components (stop_reason, diff headers,
isolation check names, reason texts) are illustrative.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from refactor_ai import __version__
from refactor_ai.analysis import AnalysisResult, analyze
from refactor_ai.contracts import (
    AnalysisReport,
    AttemptRecord,
    DecisionRequest,
    Disposition,
    ErrorResponse,
    HealthResponse,
    ModelReviewResult,
    ProviderInfo,
    ProviderMode,
    QueueInfo,
    ReferenceCase,
    ReferenceCaseSummary,
    ReferenceExpectation,
    ReferenceTest,
    ReferenceTestFailure,
    ReferenceTestsResult,
    ReviewResult,
    ReviewVerdict,
    RoleFinding,
    RubricCheck,
    RunAccepted,
    RunCreateRequest,
    RunError,
    RunList,
    RunnerInfo,
    RunRecord,
    RunStatus,
    StageTiming,
    SyntaxCheck,
    VerificationResult,
    WorkflowMode,
    WorkflowOutcome,
)
from refactor_ai.providers.fake import FAKE_MODEL, FAKE_PREFIX, FakeProvider
from refactor_ai.runs import errors
from refactor_ai.runs.components import RUNNER_DISABLED_REASON
from refactor_ai.runs.records import (
    apply_outcome,
    interrupted_record,
    new_record,
    summarize,
)
from refactor_ai.task_format import render_refactor_completion
from refactor_ai.tasks import guard_clauses

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "docs" / "architecture" / "examples"
BASE_TIME = datetime(2026, 10, 20, 9, 0, 0, tzinfo=UTC)
TASK = guard_clauses.TASK_TYPE

SHIPPING = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight > 0:
        if express:
            return weight * 3
        else:
            return weight * 2
    else:
        raise ValueError("weight must be positive")
'''

DISCOUNT = """def discount(price, member):
    if price is not None:
        if member:
            return price * 0.9
        else:
            return price
    else:
        return 0
"""

SIGN = """def sign(x):
    if x > 0:
        return 1
    elif x < 0:
        return -1
    return 0
"""

# A plausible but wrong proposal: weight 0 no longer raises ValueError.
SHIPPING_FAULTY = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight < 0:
        raise ValueError('weight must be positive')
    if express:
        return weight * 3
    return weight * 2
'''

DEEPLY_NESTED = """def scan(rows):
    for row in rows:
        if row:
            while row:
                if row[0] > 1:
                    break
"""

RUN_IDS = {
    "queued": "4b3f9a0c2d6e4f1a8b7c5d3e2f1a0b9c",
    "analyzing": "7c1e5a9b3d2f4e6a8c0b1d2e3f4a5b6c",
    "proposal_ready": "2a6d8f0b1c3e4a5b9d7f6e5d4c3b2a10",
    "uncertain": "9e8d7c6b5a4f4e3d8c2b1a0f9e8d7c6b",
    "no_change": "5f4e3d2c1b0a49f8a7e6d5c4b3a29180",
    "rejected": "c0ffee00d15ea5e0a1b2c3d4e5f60718",
    "failed": "e1d2c3b4a5f64e7d8c9b0a1f2e3d4c5b",
    "interrupted": "0a1b2c3d4e5f46a7b8c9d0e1f2a3b4c5",
}

LOCAL_PLACEHOLDER = ProviderInfo(
    provider_mode=ProviderMode.LOCAL_MODEL,
    model_id="example-org/example-code-model",
    model_revision="0" * 40,
    adapter_id="example-guard-clauses-lora",
    adapter_sha256="0" * 64,
    device="cuda:0",
    ready=True,
    detail="Illustrative placeholder identity; real values come from configs/model.local.json.",
)


@dataclass(frozen=True)
class Example:
    """One example file: the type it must validate against and its value."""

    schema: Any
    value: Any

    def render(self) -> str:
        payload = TypeAdapter(self.schema).dump_python(self.value, mode="json")
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def at(seconds: float) -> datetime:
    return BASE_TIME + timedelta(seconds=seconds)


def unified_diff(original: str, proposed: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile="original.py",
            tofile="proposed.py",
        )
    )


def changed_lines(original: str, proposed: str) -> list[int]:
    """1-based lines of the proposed code that differ from the original."""
    matcher = difflib.SequenceMatcher(a=original.splitlines(), b=proposed.splitlines())
    lines: list[int] = []
    for tag, _, _, start, end in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            lines.extend(range(start + 1, end + 1))
    return lines


def rubric_check(original: str, candidate: str) -> RubricCheck:
    result = guard_clauses.rubric(original, candidate)
    return RubricCheck(
        status="pass" if result.passed else "fail", checks=result.checks, reasons=result.reasons
    )


def not_run_verification(
    disposition: Disposition, reasons: list[str], why: str
) -> VerificationResult:
    return VerificationResult(
        syntax=SyntaxCheck(status="not_run"),
        rubric=RubricCheck(status="not_run"),
        reference_tests=ReferenceTestsResult(status="not_run", reason=why),
        model_review=ModelReviewResult(status="not_run"),
        disposition=disposition,
        disposition_reasons=reasons,
    )


def timing(stage: str, attempt: int, start: float, elapsed: float, calls: int = 0) -> StageTiming:
    return StageTiming(
        stage=stage, attempt=attempt, started_at=at(start), elapsed_s=elapsed, calls=calls
    )


# --- Reference cases -----------------------------------------------------------------


def shipping_case() -> ReferenceCase:
    return ReferenceCase(
        case_id="shipping_cost",
        task_type=TASK,
        title="Shipping cost with nested validation",
        function_name="shipping_cost",
        original_code=SHIPPING,
        reference_code=guard_clauses.to_guard_clauses(SHIPPING),
        tests=[
            ReferenceTest(args="[2, True]", expect=ReferenceExpectation(kind="return", value="6")),
            ReferenceTest(args="[2, False]", expect=ReferenceExpectation(kind="return", value="4")),
            ReferenceTest(
                args="[0, True]",
                expect=ReferenceExpectation(kind="raise", exception="ValueError"),
            ),
            ReferenceTest(
                args="[-1, False]",
                expect=ReferenceExpectation(kind="raise", exception="ValueError"),
            ),
        ],
        source_group="contract-example",
        license="Illustrative example written for the contract documentation",
        provenance="Not part of the dataset or of the demonstration fixture.",
    )


def discount_case() -> ReferenceCase:
    return ReferenceCase(
        case_id="member_discount",
        task_type=TASK,
        title="Member discount with a missing price",
        function_name="discount",
        original_code=DISCOUNT,
        reference_code=guard_clauses.to_guard_clauses(DISCOUNT),
        tests=[
            ReferenceTest(
                args="[100, True]", expect=ReferenceExpectation(kind="return", value="90.0")
            ),
            ReferenceTest(
                args="[100, False]", expect=ReferenceExpectation(kind="return", value="100")
            ),
            ReferenceTest(
                args="[None, True]", expect=ReferenceExpectation(kind="return", value="0")
            ),
        ],
        source_group="contract-example",
        license="Illustrative example written for the contract documentation",
        provenance="Not part of the dataset or of the demonstration fixture.",
    )


def case_summary(case: ReferenceCase) -> ReferenceCaseSummary:
    return ReferenceCaseSummary(
        case_id=case.case_id,
        title=case.title,
        function_name=case.function_name,
        code=case.original_code,
        test_count=len(case.tests),
    )


# --- Role outputs as the fake provider produces them ---------------------------------


def fake_analysis(code: str) -> AnalysisReport:
    check = guard_clauses.check_input(code)
    return AnalysisReport(
        supported_task=check.supported,
        findings=[
            RoleFinding(
                type=guard_clauses.FINDING_TYPE,
                start_line=item.start_line,
                end_line=item.end_line,
                reason=f"{FAKE_PREFIX} {item.reason}",
            )
            for item in check.opportunities
        ],
        unsupported_reason=None if check.supported else check.describe(),
        source="model",
    )


FAKE_EXPLANATION = f"{FAKE_PREFIX} deterministic AST transformation used for testing."
FAKE_ACCEPT = ReviewResult(
    verdict=ReviewVerdict.ACCEPT,
    reasons=[f"{FAKE_PREFIX} placeholder review; no model judged this code."],
)
SCRIPTED_REJECT = ReviewResult(
    verdict=ReviewVerdict.REJECT,
    reasons=[f"{FAKE_PREFIX} scripted review: a weight of 0 no longer raises ValueError."],
    suggested_correction="Keep zero invalid: the guard must test weight <= 0.",
)


def attempt(
    index: int,
    code: str,
    explanation: str,
    verification: VerificationResult,
    review: ReviewResult | None,
) -> AttemptRecord:
    raw = render_refactor_completion(explanation, code)
    return AttemptRecord(
        attempt=index,
        raw_output=raw,
        proposed_code=code,
        explanation=explanation,
        verification=verification,
        review=review,
        model=FAKE_MODEL,
        prompt_tokens=120 + 40 * index,
        completion_tokens=len(raw.split()),
        elapsed_s=0.01,
    )


# --- Run records ---------------------------------------------------------------------


def base_record(key: str, created: float, code: str, mode: WorkflowMode, case_id: str | None):
    return new_record(
        run_id=RUN_IDS[key],
        created_at=at(created),
        code=code,
        task_type=TASK,
        workflow_mode=mode,
        provider_mode=ProviderMode.FAKE,
        reference_case_id=case_id,
    )


def started(record: RunRecord, seconds: float, status: RunStatus) -> RunRecord:
    return record.model_copy(update={"started_at": at(seconds), "status": status})


def proposal_ready_record() -> RunRecord:
    record = started(
        base_record("proposal_ready", 120, SHIPPING, WorkflowMode.MULTI_ROLE, "shipping_cost"),
        120.4,
        RunStatus.VERIFYING,
    )
    proposed = guard_clauses.to_guard_clauses(SHIPPING)
    analysis = fake_analysis(SHIPPING)
    verification = VerificationResult(
        syntax=SyntaxCheck(status="pass"),
        rubric=rubric_check(SHIPPING, proposed),
        reference_tests=ReferenceTestsResult(
            status="pass",
            case_id="shipping_cost",
            total=4,
            passed=4,
            failed=0,
            errored=0,
            duration_s=0.42,
        ),
        model_review=ModelReviewResult(status="accept", reasons=FAKE_ACCEPT.reasons),
        disposition=Disposition.PROPOSAL_READY,
    )
    outcome = WorkflowOutcome(
        status=RunStatus.COMPLETED,
        provider_mode=ProviderMode.FAKE,
        model=FAKE_MODEL,
        analysis=analysis,
        findings=analysis.findings,
        proposed_code=proposed,
        explanation=FAKE_EXPLANATION,
        diff=unified_diff(SHIPPING, proposed),
        changed_lines=changed_lines(SHIPPING, proposed),
        review=FAKE_ACCEPT,
        verification=verification,
        attempts=[attempt(0, proposed, FAKE_EXPLANATION, verification, FAKE_ACCEPT)],
        attempt_count=1,
        call_count=3,
        stage_timings=[
            timing("validation", 0, 120.4, 0.002),
            timing("analysis", 0, 120.41, 0.01, calls=1),
            timing("generation", 0, 120.42, 0.01, calls=1),
            timing("verification", 0, 120.43, 0.45),
            timing("review", 0, 120.88, 0.01, calls=1),
        ],
        stop_reason="completed",
    )
    final = apply_outcome(record, outcome, at(121.0))
    return final.model_copy(update={"human_decision": "accepted"})


def uncertain_record() -> RunRecord:
    record = started(
        base_record("uncertain", 180, DISCOUNT, WorkflowMode.SINGLE_ROLE, None),
        180.3,
        RunStatus.VERIFYING,
    )
    proposed = guard_clauses.to_guard_clauses(DISCOUNT)
    verification = VerificationResult(
        syntax=SyntaxCheck(status="pass"),
        rubric=rubric_check(DISCOUNT, proposed),
        reference_tests=ReferenceTestsResult(
            status="not_available",
            reason="No reference case was selected, so behavior was not tested.",
        ),
        model_review=ModelReviewResult(status="not_run"),
        disposition=Disposition.UNCERTAIN,
        disposition_reasons=["Reference tests are not available; behavior was not checked."],
    )
    outcome = WorkflowOutcome(
        status=RunStatus.COMPLETED,
        provider_mode=ProviderMode.FAKE,
        model=FAKE_MODEL,
        proposed_code=proposed,
        explanation=FAKE_EXPLANATION,
        diff=unified_diff(DISCOUNT, proposed),
        changed_lines=changed_lines(DISCOUNT, proposed),
        verification=verification,
        attempts=[attempt(0, proposed, FAKE_EXPLANATION, verification, None)],
        attempt_count=1,
        call_count=1,
        stage_timings=[
            timing("validation", 0, 180.3, 0.002),
            timing("generation", 0, 180.31, 0.01, calls=1),
            timing("verification", 0, 180.32, 0.003),
        ],
        stop_reason="completed",
    )
    return apply_outcome(record, outcome, at(180.4))


def no_change_record() -> RunRecord:
    record = started(
        base_record("no_change", 240, SIGN, WorkflowMode.MULTI_ROLE, None),
        240.2,
        RunStatus.QUEUED,
    )
    check = guard_clauses.check_input(SIGN)
    reasons = [f"{code}: {guard_clauses.reason_text(code)}" for code in check.reasons]
    outcome = WorkflowOutcome(
        status=RunStatus.COMPLETED,
        provider_mode=ProviderMode.FAKE,
        analysis=AnalysisReport(
            supported_task=False, unsupported_reason=check.describe(), source="static"
        ),
        verification=not_run_verification(Disposition.NO_CHANGE, reasons, "No proposal to test."),
        stage_timings=[timing("validation", 0, 240.2, 0.002)],
        stop_reason="no_change",
    )
    return apply_outcome(record, outcome, at(240.21))


def rejected_record() -> RunRecord:
    record = started(
        base_record("rejected", 300, SHIPPING, WorkflowMode.MULTI_ROLE, "shipping_cost"),
        300.2,
        RunStatus.VERIFYING,
    )
    analysis = fake_analysis(SHIPPING)
    failing_tests = ReferenceTestsResult(
        status="fail",
        case_id="shipping_cost",
        total=4,
        passed=3,
        failed=1,
        errored=0,
        duration_s=0.44,
        failures=[
            ReferenceTestFailure(
                index=2,
                kind="missing_exception",
                detail="Expected ValueError, but the call returned 0.",
            )
        ],
    )
    explanation = f"{FAKE_PREFIX} scripted faulty proposal used to illustrate a rejection."

    def verification(review: ReviewResult) -> VerificationResult:
        return VerificationResult(
            syntax=SyntaxCheck(status="pass"),
            rubric=rubric_check(SHIPPING, SHIPPING_FAULTY),
            reference_tests=failing_tests,
            model_review=ModelReviewResult(status="reject", reasons=review.reasons),
            disposition=Disposition.REJECTED,
            disposition_reasons=[
                "1 of 4 reference tests failed.",
                "The model review rejected the proposal.",
            ],
        )

    final = verification(SCRIPTED_REJECT)
    outcome = WorkflowOutcome(
        status=RunStatus.COMPLETED,
        provider_mode=ProviderMode.FAKE,
        model=FAKE_MODEL,
        analysis=analysis,
        findings=analysis.findings,
        proposed_code=SHIPPING_FAULTY,
        explanation=explanation,
        diff=unified_diff(SHIPPING, SHIPPING_FAULTY),
        changed_lines=changed_lines(SHIPPING, SHIPPING_FAULTY),
        review=SCRIPTED_REJECT,
        verification=final,
        attempts=[
            attempt(0, SHIPPING_FAULTY, explanation, final, SCRIPTED_REJECT),
            attempt(1, SHIPPING_FAULTY, explanation, final, SCRIPTED_REJECT),
        ],
        attempt_count=2,
        call_count=5,
        stage_timings=[
            timing("validation", 0, 300.2, 0.002),
            timing("analysis", 0, 300.21, 0.01, calls=1),
            timing("generation", 0, 300.22, 0.01, calls=1),
            timing("verification", 0, 300.23, 0.46),
            timing("review", 0, 300.69, 0.01, calls=1),
            timing("generation", 1, 300.75, 0.01, calls=1),
            timing("verification", 1, 300.76, 0.46),
            timing("review", 1, 301.22, 0.01, calls=1),
        ],
        stop_reason="correction_limit_reached",
    )
    return apply_outcome(record, outcome, at(301.3))


def failed_record() -> RunRecord:
    record = started(
        base_record("failed", 360, SHIPPING, WorkflowMode.MULTI_ROLE, "shipping_cost"),
        360.2,
        RunStatus.GENERATING,
    )
    analysis = fake_analysis(SHIPPING)
    error = RunError(code="timeout", message="Generation exceeded 120.0 s", stage="generation")
    outcome = WorkflowOutcome(
        status=RunStatus.FAILED,
        provider_mode=ProviderMode.FAKE,
        model=FAKE_MODEL,
        analysis=analysis,
        findings=analysis.findings,
        verification=not_run_verification(
            Disposition.FAILED, [f"{error.code}: {error.message}"], "No proposal to test."
        ),
        attempts=[AttemptRecord(attempt=0, model=FAKE_MODEL, elapsed_s=120.0)],
        attempt_count=1,
        call_count=2,
        stage_timings=[
            timing("validation", 0, 360.2, 0.002),
            timing("analysis", 0, 360.21, 0.01, calls=1),
            timing("generation", 0, 360.22, 120.0, calls=1),
        ],
        stop_reason="provider_error",
        error=error,
    )
    return apply_outcome(record, outcome, at(480.3))


def interrupted_example() -> RunRecord:
    # The service stopped while this run was generating; the restart at 09:15 marked it.
    record = started(
        base_record("interrupted", 540, DISCOUNT, WorkflowMode.MULTI_ROLE, "member_discount"),
        540.2,
        RunStatus.GENERATING,
    )
    return interrupted_record(record, at(900.0))


def analyzing_record() -> RunRecord:
    # Created after the restart that interrupted the previous run.
    return started(
        base_record("analyzing", 960, DISCOUNT, WorkflowMode.MULTI_ROLE, None),
        960.1,
        RunStatus.ANALYZING,
    )


def queued_record() -> RunRecord:
    # Waiting behind the analyzing run: one worker processes runs in order.
    return base_record("queued", 965, SHIPPING, WorkflowMode.MULTI_ROLE, "shipping_cost")


# --- Errors --------------------------------------------------------------------------


def syntax_error_example() -> ErrorResponse:
    code = "def shipping_cost(weight express):\n    return weight\n"
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return errors.invalid_syntax(exc).body()
    raise AssertionError("the example code must not parse")


def validation_error_example() -> ErrorResponse:
    return errors.validation_error(
        [
            {
                "loc": ("body", "code"),
                "msg": "Value error, code must not be blank",
                "type": "value_error",
            }
        ]
    ).body()


# --- Assembly ------------------------------------------------------------------------


def build_examples() -> dict[str, Example]:
    shipping, discount = shipping_case(), discount_case()
    records = {
        "queued": queued_record(),
        "analyzing": analyzing_record(),
        "proposal_ready": proposal_ready_record(),
        "uncertain": uncertain_record(),
        "no_change": no_change_record(),
        "rejected": rejected_record(),
        "failed": failed_record(),
        "interrupted": interrupted_example(),
    }
    newest_first = sorted(records.values(), key=lambda r: r.created_at, reverse=True)
    fake_info = FakeProvider().info()
    queued = records["queued"]
    examples = {
        "run_create_request.json": Example(
            RunCreateRequest,
            RunCreateRequest(
                code=SHIPPING,
                workflow_mode=WorkflowMode.MULTI_ROLE,
                reference_case_id=shipping.case_id,
            ),
        ),
        "run_accepted.json": Example(
            RunAccepted,
            RunAccepted(
                run_id=queued.run_id,
                status=RunStatus.QUEUED,
                poll_url=f"/api/v1/runs/{queued.run_id}",
            ),
        ),
        "run_list.json": Example(
            RunList, RunList(runs=[summarize(r) for r in newest_first], limit=20)
        ),
        "decision_request.json": Example(DecisionRequest, DecisionRequest(decision="accepted")),
        "reference_cases.json": Example(
            list[ReferenceCaseSummary], [case_summary(shipping), case_summary(discount)]
        ),
        "health_fake.json": Example(
            HealthResponse,
            HealthResponse(
                version=__version__,
                mode=ProviderMode.FAKE,
                provider=fake_info,
                runner=RunnerInfo(enabled=False, reason=RUNNER_DISABLED_REASON),
                queue=QueueInfo(max_pending=4, pending=0),
            ),
        ),
        "health_local.json": Example(
            HealthResponse,
            HealthResponse(
                version=__version__,
                mode=ProviderMode.LOCAL_MODEL,
                provider=LOCAL_PLACEHOLDER,
                runner=RunnerInfo(
                    enabled=True,
                    isolation={
                        "separate_process": True,
                        "time_limit": True,
                        "memory_limit": True,
                        "process_limit": True,
                        "no_network": True,
                        "empty_environment": True,
                        "temporary_directory": True,
                    },
                ),
                queue=QueueInfo(max_pending=4, pending=1),
            ),
        ),
        "analysis_report.json": Example(AnalysisReport, fake_analysis(SHIPPING)),
        "review_result.json": Example(ReviewResult, SCRIPTED_REJECT),
        "analyze_response.json": Example(AnalysisResult, analyze(DEEPLY_NESTED)),
        "error_validation_error.json": Example(ErrorResponse, validation_error_example()),
        "error_invalid_syntax.json": Example(ErrorResponse, syntax_error_example()),
        "error_unknown_reference_case.json": Example(
            ErrorResponse, errors.unknown_reference_case("missing_case").body()
        ),
        "error_reference_case_mismatch.json": Example(
            ErrorResponse, errors.reference_case_mismatch(shipping.case_id).body()
        ),
        "error_busy.json": Example(ErrorResponse, errors.busy(4).body()),
        "error_run_not_found.json": Example(ErrorResponse, errors.run_not_found().body()),
        "error_proposal_unavailable.json": Example(
            ErrorResponse, errors.proposal_unavailable(errors.PROPOSAL_MISSING).body()
        ),
        "error_payload_too_large.json": Example(ErrorResponse, errors.payload_too_large().body()),
        "error_internal_error.json": Example(ErrorResponse, errors.internal_error().body()),
    }
    for key, record in records.items():
        examples[f"run_record_{key}.json"] = Example(RunRecord, record)
    _check_consistency(records)
    return dict(sorted(examples.items()))


def _check_consistency(records: dict[str, RunRecord]) -> None:
    """Guard the examples against drifting away from the task module's real behavior."""
    assert guard_clauses.check_input(SHIPPING).supported
    assert guard_clauses.check_input(DISCOUNT).supported
    assert not guard_clauses.check_input(SIGN).supported
    assert guard_clauses.rubric(SHIPPING, SHIPPING_FAULTY).passed
    expected = {
        "queued": (RunStatus.QUEUED, None),
        "analyzing": (RunStatus.ANALYZING, None),
        "proposal_ready": (RunStatus.COMPLETED, Disposition.PROPOSAL_READY),
        "uncertain": (RunStatus.COMPLETED, Disposition.UNCERTAIN),
        "no_change": (RunStatus.COMPLETED, Disposition.NO_CHANGE),
        "rejected": (RunStatus.COMPLETED, Disposition.REJECTED),
        "failed": (RunStatus.FAILED, Disposition.FAILED),
        "interrupted": (RunStatus.FAILED, Disposition.FAILED),
    }
    for key, (status, disposition) in expected.items():
        summary = summarize(records[key])
        assert (summary.status, summary.disposition) == (status, disposition), key


def write_examples(directory: Path = EXAMPLES_DIR) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, example in build_examples().items():
        path = directory / name
        text = example.render()
        if not path.exists() or path.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            path.write_text(text, encoding="utf-8", newline="\n")
            written.append(name)
    return written


def stale_examples(directory: Path = EXAMPLES_DIR) -> list[str]:
    """Names of missing, outdated or unexpected example files."""
    expected = build_examples()
    problems = []
    for name, example in expected.items():
        path = directory / name
        if not path.exists():
            problems.append(f"missing: {name}")
        elif path.read_text(encoding="utf-8").replace("\r\n", "\n") != example.render():
            problems.append(f"stale: {name}")
    for path in sorted(directory.glob("*.json")):
        if path.name not in expected:
            problems.append(f"unexpected: {path.name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify the files; write nothing")
    args = parser.parse_args(argv)
    if args.check:
        problems = stale_examples()
        if problems:
            print("Contract examples are out of date:\n" + "\n".join(problems))
            print("Regenerate: python -m uv run python scripts/export_contract_examples.py")
            return 1
        print(f"{len(build_examples())} contract examples are up to date")
        return 0
    written = write_examples()
    print(f"Wrote {len(written)} of {len(build_examples())} contract examples")
    for name in written:
        print(f"  {name}")
    unexpected = [p for p in stale_examples() if p.startswith("unexpected")]
    if unexpected:
        print("Remove files that no example produces:\n" + "\n".join(unexpected))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

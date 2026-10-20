"""Write the contract example JSON files under docs/architecture/examples/.

Each example is built from the Pydantic models in refactor_ai.contracts and from the
service's own code, validated, and written with a fixed layout, so the output is
deterministic. tests/test_contract_examples.py fails when a file is missing, stale,
unexpected or invalid.

    python -m uv run python scripts/export_contract_examples.py                  # write
    python -m uv run python scripts/export_contract_examples.py --check          # verify
    python -m uv run python scripts/export_contract_examples.py --verify-runner  # replay check

Completed and failed run records come from the real coordinator
(refactor_ai.agents.coordinator.run_workflow) with the labelled FakeProvider, so stop
reasons, warnings and reason texts are the implementation's own. Reference-test results
come from a replay runner holding results captured from the real reference runner
(refactor_ai.verification.create_runner); --verify-runner runs the real runner again and
compares. Timings are replaced by fixed values. The examples illustrate the schema; none
of them is a model result. The local-model identity and the reference cases are
placeholders written for this page.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from refactor_ai import __version__
from refactor_ai.agents.coordinator import run_workflow
from refactor_ai.analysis import AnalysisResult, analyze
from refactor_ai.contracts import (
    AnalysisReport,
    DecisionRequest,
    Disposition,
    ErrorResponse,
    HealthResponse,
    ProviderError,
    ProviderErrorCode,
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
    Role,
    RunAccepted,
    RunCreateRequest,
    RunList,
    RunnerInfo,
    RunRecord,
    RunStatus,
    WorkflowMode,
    WorkflowOutcome,
    WorkflowRequest,
)
from refactor_ai.providers.fake import FAKE_PREFIX, FakeProvider
from refactor_ai.runs import errors
from refactor_ai.runs.components import (
    ADAPTER_MISSING_REASON,
    RUNNER_DISABLED_REASON,
    provider_health_info,
)
from refactor_ai.runs.errors import RunErrorCode
from refactor_ai.runs.records import (
    apply_outcome,
    failed_record,
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
    "adapter_unavailable": "a7d0c3e1b2f44a5c9e8d7b6a5f4e3d21",
    "interrupted": "0a1b2c3d4e5f46a7b8c9d0e1f2a3b4c5",
}

LOCAL_PLACEHOLDER = ProviderInfo(
    provider_mode=ProviderMode.LOCAL_MODEL,
    model_id="example-org/example-code-model",
    model_revision="0" * 40,
    adapter_id="example-guard-clauses-lora",
    adapter_sha256="0" * 64,
    device="cuda",
    ready=True,
    detail="Illustrative placeholder identity; real values come from configs/model.local.json.",
)

# The isolation self-check names reported by the real reference runner.
RUNNER_ISOLATION = dict.fromkeys(
    (
        "platform_supported",
        "interpreter_found",
        "basic_execution",
        "os_limits_applied",
        "audit_hook_installed",
        "environment_scrubbed",
        "working_directory_isolated",
        "workdir_removed",
        "network_blocked",
        "file_write_blocked",
        "host_read_blocked",
        "subprocess_blocked",
        "native_code_blocked",
        "introspection_blocked",
        "process_limit_enforced",
        "memory_limit_enforced",
        "timeout_enforced",
        "process_cleanup",
        "cpu_limit_enforced",
    ),
    True,
)

# Fixed stage durations replacing the measured ones (seconds).
STAGE_SECONDS = {
    "validation": 0.002,
    "analysis": 0.01,
    "generation": 0.01,
    "verification": 0.12,
    "review": 0.01,
}


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


# --- Reference cases and the replayed reference runner --------------------------------


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


@dataclass(frozen=True)
class Replay:
    """A reference-test result captured from the real runner for one candidate."""

    case: ReferenceCase
    candidate: str
    result: ReferenceTestsResult


def captured_results() -> list[Replay]:
    """Results of refactor_ai.verification.create_runner() on 2026-10-20 (durations fixed).

    --verify-runner runs the real runner on the same inputs and compares.
    """
    case = shipping_case()
    return [
        Replay(
            case,
            guard_clauses.to_guard_clauses(SHIPPING) or "",
            ReferenceTestsResult(
                status="pass",
                case_id=case.case_id,
                total=4,
                passed=4,
                failed=0,
                errored=0,
                duration_s=0.125,
            ),
        ),
        Replay(
            case,
            SHIPPING_FAULTY,
            ReferenceTestsResult(
                status="fail",
                case_id=case.case_id,
                total=4,
                passed=3,
                failed=1,
                errored=0,
                reason="1 of 4 reference tests failed.",
                duration_s=0.109,
                failures=[
                    ReferenceTestFailure(
                        index=2,
                        kind="missing_exception",
                        detail="shipping_cost(0, True) returned 0 (int); expected ValueError "
                        "to be raised.",
                    )
                ],
            ),
        ),
    ]


class ReplayRunner:
    """A ReferenceRunner that returns the captured results; it executes nothing."""

    def __init__(self, replays: Iterable[Replay]) -> None:
        self._replays = list(replays)

    def info(self) -> RunnerInfo:
        return RunnerInfo(enabled=True, isolation=RUNNER_ISOLATION)

    def run(self, case: ReferenceCase, candidate_code: str) -> ReferenceTestsResult:
        for replay in self._replays:
            if replay.case.case_id == case.case_id and (
                replay.candidate.rstrip() == candidate_code.rstrip()
            ):
                return replay.result.model_copy(deep=True)
        raise KeyError(f"No captured runner result for case {case.case_id} and this candidate")


def verify_runner() -> list[str]:
    """Run the real reference runner on the captured inputs; list any difference."""
    from refactor_ai.verification import create_runner

    runner = create_runner()
    info = runner.info()
    if not info.enabled:
        return [f"the real runner is disabled here: {info.reason}"]
    problems = []
    for replay in captured_results():
        live = runner.run(replay.case, replay.candidate)
        expected = replay.result.model_dump(exclude={"duration_s"})
        if live.model_dump(exclude={"duration_s"}) != expected:
            problems.append(f"{replay.case.case_id}: captured {expected}, live {live.model_dump()}")
    return problems


# --- Run records ---------------------------------------------------------------------


def base_record(
    key: str,
    created: float,
    code: str,
    mode: WorkflowMode,
    case_id: str | None,
    *,
    use_adapter: bool = False,
) -> RunRecord:
    return new_record(
        run_id=RUN_IDS[key],
        created_at=at(created),
        code=code,
        task_type=TASK,
        workflow_mode=mode,
        provider_mode=ProviderMode.FAKE,
        reference_case_id=case_id,
        refactor_use_adapter=use_adapter,
    )


def started(record: RunRecord, seconds: float, status: RunStatus) -> RunRecord:
    return record.model_copy(update={"started_at": at(seconds), "status": status})


def fixed_timings(
    outcome: WorkflowOutcome, start: datetime, overrides: dict[str, float]
) -> tuple[WorkflowOutcome, datetime]:
    """Replace measured stage timings and attempt durations with fixed values."""
    clock = start
    timings = []
    generation: dict[int, float] = {}
    for timing in outcome.stage_timings:
        elapsed = overrides.get(timing.stage, STAGE_SECONDS[timing.stage])
        timings.append(timing.model_copy(update={"started_at": clock, "elapsed_s": elapsed}))
        if timing.stage == "generation":
            generation[timing.attempt] = elapsed
        clock += timedelta(seconds=elapsed)
    attempts = [
        attempt.model_copy(
            update={"elapsed_s": None if attempt.elapsed_s is None else generation[attempt.attempt]}
        )
        for attempt in outcome.attempts
    ]
    return outcome.model_copy(update={"stage_timings": timings, "attempts": attempts}), clock


def coordinated_record(
    key: str,
    created: float,
    code: str,
    mode: WorkflowMode,
    case: ReferenceCase | None = None,
    script: dict[Role, list] | None = None,
    timing_overrides: dict[str, float] | None = None,
) -> RunRecord:
    """A finished record as the service stores it, from the real coordinator."""
    record = started(
        base_record(key, created, code, mode, None if case is None else case.case_id),
        created + 0.2,
        RunStatus.QUEUED,
    )
    outcome = run_workflow(
        WorkflowRequest(code=record.original_code, task_type=record.task_type, reference_case=case),
        provider=FakeProvider(script=script),
        settings=record.settings,
        runner=ReplayRunner(captured_results()),
    )
    outcome, finished = fixed_timings(outcome, record.started_at, timing_overrides or {})
    return apply_outcome(record, outcome, finished)


def scripted_review(verdict: str, reason: str, correction: str | None = None) -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "reasons": [f"{FAKE_PREFIX} {reason}"],
            "suggested_correction": correction,
        }
    )


def run_records() -> dict[str, RunRecord]:
    shipping = shipping_case()
    faulty = render_refactor_completion(
        f"{FAKE_PREFIX} scripted faulty proposal used to illustrate a rejection.", SHIPPING_FAULTY
    )
    reject = scripted_review(
        "reject",
        "scripted review: a weight of 0 no longer raises ValueError.",
        "Keep zero invalid: the guard must test weight <= 0.",
    )
    timeout = ProviderError(code=ProviderErrorCode.TIMEOUT, message="Generation exceeded 120.0 s")
    multi, single = WorkflowMode.MULTI_ROLE, WorkflowMode.SINGLE_ROLE
    proposal_ready = coordinated_record("proposal_ready", 120, SHIPPING, multi, shipping)
    adapter_record = started(
        base_record("adapter_unavailable", 500, SHIPPING, multi, None, use_adapter=True),
        500.1,
        RunStatus.QUEUED,
    )
    interrupted = started(
        base_record("interrupted", 540, DISCOUNT, multi, "member_discount"),
        540.2,
        RunStatus.GENERATING,
    )
    return {
        "proposal_ready": proposal_ready.model_copy(update={"human_decision": "accepted"}),
        "uncertain": coordinated_record("uncertain", 180, DISCOUNT, single),
        "no_change": coordinated_record("no_change", 240, SIGN, multi),
        "rejected": coordinated_record(
            "rejected",
            300,
            SHIPPING,
            multi,
            shipping,
            script={Role.REFACTOR: [faulty, faulty], Role.REVIEW: [reject, reject]},
        ),
        "failed": coordinated_record(
            "failed",
            360,
            SHIPPING,
            multi,
            shipping,
            script={Role.REFACTOR: [timeout]},
            timing_overrides={"generation": 120.0},
        ),
        # What the service stores when the adapter is requested but not configured.
        "adapter_unavailable": failed_record(
            adapter_record,
            at(500.1),
            RunErrorCode.ADAPTER_UNAVAILABLE,
            ADAPTER_MISSING_REASON,
            None,
        ),
        # The service stopped while this run was generating; the restart at 09:15 marked it.
        "interrupted": interrupted_record(interrupted, at(900.0)),
        # Created after that restart; one worker processes runs in order.
        "analyzing": started(
            base_record("analyzing", 960, DISCOUNT, multi, None), 960.1, RunStatus.ANALYZING
        ),
        "queued": base_record("queued", 965, SHIPPING, multi, "shipping_cost"),
    }


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


# --- Health --------------------------------------------------------------------------


def health(
    provider: ProviderInfo,
    runner: RunnerInfo,
    *,
    pending: int = 0,
    use_adapter: bool = False,
    warming_up: bool = False,
) -> HealthResponse:
    return HealthResponse(
        version=__version__,
        mode=provider.provider_mode,
        provider=provider_health_info(provider, use_adapter=use_adapter, warming_up=warming_up),
        runner=runner,
        queue=QueueInfo(max_pending=4, pending=pending),
        refactor_use_adapter=use_adapter,
    )


def health_examples() -> dict[str, HealthResponse]:
    runner_enabled = RunnerInfo(enabled=True, isolation=RUNNER_ISOLATION)
    no_adapter = LOCAL_PLACEHOLDER.model_copy(update={"adapter_id": None, "adapter_sha256": None})
    loading = LOCAL_PLACEHOLDER.model_copy(update={"ready": False})
    return {
        "health_fake.json": health(
            FakeProvider().info(), RunnerInfo(enabled=False, reason=RUNNER_DISABLED_REASON)
        ),
        "health_local.json": health(LOCAL_PLACEHOLDER, runner_enabled, pending=1, use_adapter=True),
        "health_local_loading.json": health(
            loading, runner_enabled, use_adapter=True, warming_up=True
        ),
        "health_local_adapter_missing.json": health(no_adapter, runner_enabled, use_adapter=True),
    }


# --- Assembly ------------------------------------------------------------------------


def build_examples() -> dict[str, Example]:
    shipping, discount = shipping_case(), discount_case()
    records = run_records()
    newest_first = sorted(records.values(), key=lambda r: r.created_at, reverse=True)
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
        "analysis_report.json": Example(AnalysisReport, records["proposal_ready"].analysis),
        "review_result.json": Example(ReviewResult, records["rejected"].review),
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
    for name, value in health_examples().items():
        examples[name] = Example(HealthResponse, value)
    for key, record in records.items():
        examples[f"run_record_{key}.json"] = Example(RunRecord, record)
    _check_consistency(records)
    return dict(sorted(examples.items()))


EXPECTED_STATES = {
    "queued": (RunStatus.QUEUED, None),
    "analyzing": (RunStatus.ANALYZING, None),
    "proposal_ready": (RunStatus.COMPLETED, Disposition.PROPOSAL_READY),
    "uncertain": (RunStatus.COMPLETED, Disposition.UNCERTAIN),
    "no_change": (RunStatus.COMPLETED, Disposition.NO_CHANGE),
    "rejected": (RunStatus.COMPLETED, Disposition.REJECTED),
    "failed": (RunStatus.FAILED, Disposition.FAILED),
    "adapter_unavailable": (RunStatus.FAILED, Disposition.FAILED),
    "interrupted": (RunStatus.FAILED, Disposition.FAILED),
}


def _check_consistency(records: dict[str, RunRecord]) -> None:
    """Fail loudly if the coordinator no longer produces the states the files describe."""
    assert guard_clauses.check_input(SHIPPING).supported
    assert guard_clauses.check_input(DISCOUNT).supported
    assert not guard_clauses.check_input(SIGN).supported
    assert guard_clauses.rubric(SHIPPING, SHIPPING_FAULTY).passed
    assert set(records) == set(EXPECTED_STATES)
    for key, (status, disposition) in EXPECTED_STATES.items():
        summary = summarize(records[key])
        assert (summary.status, summary.disposition) == (status, disposition), (
            key,
            summary.status,
            summary.disposition,
        )


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
    parser.add_argument(
        "--verify-runner",
        action="store_true",
        help="run the real reference runner and compare it with the captured results",
    )
    args = parser.parse_args(argv)
    if args.verify_runner:
        problems = verify_runner()
        if problems:
            print("Captured runner results differ from the real runner:\n" + "\n".join(problems))
            return 1
        print("Captured runner results match the real reference runner")
        return 0
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

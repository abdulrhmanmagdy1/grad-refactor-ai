"""Run evaluation arms through the workflow coordinator and write case-level records.

The workflow function is injected (tests pass a stub returning WorkflowOutcome objects);
by default refactor_ai.agents.coordinator.run_workflow is imported lazily. Every
provider call goes through MeteredProvider, so calls, tokens, latency and model identity
are measured by the harness itself rather than taken from the workflow's own counters.
The harness rechecks syntax and the task rubric of every final proposal without
executing it; reference tests are executed only by the injected trusted runner inside
the workflow. Records are appended and flushed one by one, and an existing output file
is never overwritten, so every attempt is retained.
"""

from __future__ import annotations

import ast
import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from refactor_ai.contracts import (
    GenerationRequest,
    GenerationResult,
    ProviderInfo,
    ProviderMode,
    Role,
    WorkflowOutcome,
    WorkflowRequest,
    WorkflowSettings,
)
from refactor_ai.evaluation import resources
from refactor_ai.evaluation.cases import to_reference_case
from refactor_ai.evaluation.protocol import ARM_SPECS, arm_settings
from refactor_ai.evaluation.records import (
    CallMeasurement,
    EvaluationRecord,
    Recheck,
    ReferenceTestSummary,
)
from refactor_ai.tasks import guard_clauses

WorkflowFn = Callable[..., WorkflowOutcome]
EVALUATOR = "scripts/evaluate.py (automatic: workflow verification plus harness recheck)"
FAILED_STOP_REASONS = {
    "run_timeout": "run_timeout",
    "unparseable_output": "unparseable_output",
    "invalid_settings": "invalid_settings",
    "reference_case_mismatch": "reference_case_mismatch",
    "internal_error": "internal_error",
}


class MeteredProvider:
    """Delegates to a provider and keeps every (request, result) pair it served."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self._calls: list[tuple[GenerationRequest, GenerationResult]] = []

    @property
    def mode(self) -> ProviderMode:
        return self._inner.mode

    def info(self) -> ProviderInfo:
        return self._inner.info()

    def close(self) -> None:
        self._inner.close()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        result = self._inner.generate(request)
        self._calls.append((request, result))
        return result

    def take_calls(self) -> list[tuple[GenerationRequest, GenerationResult]]:
        calls, self._calls = self._calls, []
        return calls

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def default_workflow() -> WorkflowFn:
    from refactor_ai.agents.coordinator import run_workflow  # lazy: workflow workstream

    return run_workflow


@dataclass
class EvaluationContext:
    evaluation_id: str
    protocol_version: str
    protocol_status: str
    dataset_sha256: str
    split: str
    split_sha256: str
    code_sha: str | None
    measure_gpu: bool = False
    evaluator: str = EVALUATOR


def _sha256(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_failure(outcome: WorkflowOutcome | None, harness_error: str | None) -> str:
    if harness_error is not None or outcome is None:
        return "harness_exception"
    if outcome.status == "completed":
        return "none"
    if outcome.stop_reason == "provider_error":
        code = outcome.error.code if outcome.error else None
        return "provider_timeout" if code == "timeout" else "provider_error"
    return FAILED_STOP_REASONS.get(outcome.stop_reason or "", "failed_other")


def _recheck(original: str, proposed: str | None, syntax: str, rubric: str) -> Recheck:
    """Independent syntax (ast.parse only) and rubric check, same semantics as the workflow:
    the rubric is not_run when the proposal does not parse. Nothing is executed."""
    if proposed is None:
        return Recheck(syntax="no_output", rubric="no_output")
    try:
        ast.parse(proposed)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        recheck = Recheck(syntax="fail", rubric="not_run")
    else:
        try:
            result = guard_clauses.rubric(original, proposed)
        except (ValueError, RecursionError, MemoryError):
            recheck = Recheck(
                syntax="pass", rubric="fail", rubric_failed_checks=["evaluation_error"]
            )
        else:
            recheck = Recheck(
                syntax="pass",
                rubric="pass" if result.passed else "fail",
                rubric_failed_checks=sorted(k for k, ok in result.checks.items() if not ok),
            )
    if syntax != "not_run":
        recheck.agrees_with_workflow = syntax == recheck.syntax and rubric == recheck.rubric
    return recheck


def _calls(raw: list[tuple[GenerationRequest, GenerationResult]]) -> list[CallMeasurement]:
    measured = []
    for index, (request, result) in enumerate(raw):
        measured.append(
            CallMeasurement(
                index=index,
                role=request.role.value,
                use_adapter=request.use_adapter,
                model=result.model.model_dump(mode="json") if result.model else None,
                elapsed_s=result.elapsed_s,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                finish_reason=result.finish_reason,
                error_code=result.error.code.value if result.error else None,
                output=result.text,
            )
        )
    return measured


def _token_total(calls: list[CallMeasurement], field: str, nulls: dict[str, str]) -> int | None:
    values = [getattr(call, field) for call in calls]
    if not calls:
        nulls[field] = "no provider call was made"
        return None
    missing = sum(value is None for value in values)
    if missing:
        nulls[field] = f"the provider reported no {field} for {missing} of {len(values)} calls"
        return None
    return sum(values)


def _budget_warnings(
    arm: str, settings: WorkflowSettings, calls: list[CallMeasurement]
) -> list[str]:
    warnings = []
    if len(calls) > settings.max_calls:
        warnings.append(
            f"budget_violation: {len(calls)} calls exceed max_calls {settings.max_calls}"
        )
    adapter = ARM_SPECS[arm].refactor_use_adapter
    for call in calls:
        expected = adapter if call.role == Role.REFACTOR.value else False
        if call.use_adapter != expected:
            warnings.append(
                f"adapter_flag_mismatch: call {call.index} ({call.role}) use_adapter="
                f"{call.use_adapter}, arm {arm} expects {expected}"
            )
        reported = (call.model or {}).get("use_adapter")
        if call.model is not None and reported != call.use_adapter:
            warnings.append(
                f"adapter_identity_mismatch: call {call.index} requested use_adapter="
                f"{call.use_adapter} but the provider reported {reported}"
            )
    return warnings


def build_record(
    record: dict,
    arm: str,
    settings: WorkflowSettings,
    outcome: WorkflowOutcome | None,
    harness_error: str | None,
    raw_calls: list[tuple[GenerationRequest, GenerationResult]],
    latency_s: float,
    started_at: str,
    context: EvaluationContext,
    provider,
) -> EvaluationRecord:
    nulls: dict[str, str] = {}
    calls = _calls(raw_calls)
    verification = outcome.verification if outcome is not None else None
    if verification is not None:
        syntax = verification.syntax.status
        rubric = verification.rubric.status
        rubric_failed = sorted(k for k, ok in verification.rubric.checks.items() if not ok)
        tests = verification.reference_tests
        test_summary = ReferenceTestSummary(
            status=tests.status,
            total=tests.total,
            passed=tests.passed,
            failed=tests.failed,
            errored=tests.errored,
            reason=tests.reason,
        )
        review = verification.model_review.status
        disposition = verification.disposition.value
        disposition_reasons = list(verification.disposition_reasons)
    else:
        syntax = rubric = review = "not_run"
        rubric_failed = []
        reason = harness_error or "the workflow returned no verification"
        test_summary = ReferenceTestSummary(status="not_run", reason=reason)
        disposition = "failed"
        disposition_reasons = [reason]
    proposed = outcome.proposed_code if outcome is not None else None
    if proposed is None:
        nulls["proposed_code"] = "the workflow produced no proposal"
    run_status = None if outcome is None else outcome.status.value
    pid = getattr(provider, "worker_pid", None)
    peak, peak_reason = resources.process_peak_rss_mb(pid)
    if peak is None:
        nulls["worker_peak_rss_mb"] = peak_reason or "unavailable"
    gpu, gpu_reason = (None, "GPU memory was not sampled for this run")
    if context.measure_gpu:
        gpu, gpu_reason = resources.gpu_memory_used_mb()
    if gpu is None:
        nulls["gpu_memory_used_mb"] = gpu_reason or "unavailable"
    warnings = list(outcome.warnings) if outcome is not None else []
    warnings += _budget_warnings(arm, settings, calls)
    if harness_error:
        warnings.append(f"harness_exception: {harness_error}")
    models = []
    for call in calls:
        if call.model is not None and call.model not in models:
            models.append(call.model)
    prompt_tokens = _token_total(calls, "prompt_tokens", nulls)
    completion_tokens = _token_total(calls, "completion_tokens", nulls)
    if outcome is not None and outcome.provider_mode == ProviderMode.FAKE:
        nulls["model_evidence"] = "fake provider: outputs and token counts are not model inference"
    return EvaluationRecord(
        evaluation_id=context.evaluation_id,
        protocol_version=context.protocol_version,
        protocol_status=context.protocol_status,
        arm=arm,
        case_id=record["id"],
        split=record["split"],
        source=record["source"],
        source_group=record["source_group"],
        dataset_sha256=context.dataset_sha256,
        split_sha256=context.split_sha256,
        code_sha=context.code_sha,
        started_at=started_at,
        provider_mode=(outcome.provider_mode.value if outcome is not None else provider.mode.value),
        model=(outcome.model.model_dump(mode="json") if outcome and outcome.model else None),
        models_used=models,
        settings=settings.model_dump(mode="json"),
        generation_seed=settings.generation[Role.REFACTOR].seed,
        input_sha256=_sha256(record["original_code"]),
        output_sha256=_sha256(proposed),
        proposed_code=proposed,
        explanation=outcome.explanation if outcome is not None else None,
        run_status=run_status,
        disposition=disposition,
        disposition_reasons=disposition_reasons,
        stop_reason=outcome.stop_reason if outcome is not None else None,
        error=(
            outcome.error.model_dump(mode="json")
            if outcome is not None and outcome.error
            else (
                {"code": "harness_exception", "message": harness_error} if harness_error else None
            )
        ),
        failure_type=classify_failure(outcome, harness_error),
        syntax=syntax,
        rubric=rubric,
        rubric_failed_checks=rubric_failed,
        reference_tests=test_summary,
        model_review=review,
        recheck=_recheck(record["original_code"], proposed, syntax, rubric),
        proposal_ready=(run_status == "completed" and disposition == "proposal_ready"),
        attempt_count=outcome.attempt_count if outcome is not None else None,
        reported_call_count=outcome.call_count if outcome is not None else None,
        calls=calls,
        call_count=len(calls),
        calls_by_role=dict(sorted(Counter(call.role for call in calls).items())),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_s=round(latency_s, 6),
        stage_timings=(
            [timing.model_dump(mode="json") for timing in outcome.stage_timings]
            if outcome is not None
            else []
        ),
        worker_peak_rss_mb=peak,
        gpu_memory_used_mb=gpu,
        null_reasons=nulls,
        warnings=warnings,
        evaluator=context.evaluator,
    )


def evaluate_case(
    record: dict,
    arm: str,
    *,
    workflow: WorkflowFn,
    provider: MeteredProvider,
    runner,
    context: EvaluationContext,
) -> EvaluationRecord:
    settings = arm_settings(arm)
    request = WorkflowRequest(
        code=record["original_code"],
        task_type=record["refactoring_type"],
        reference_case=to_reference_case(record),
    )
    provider.take_calls()
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    outcome: WorkflowOutcome | None = None
    harness_error: str | None = None
    start = time.perf_counter()
    try:
        outcome = workflow(request, provider=provider, settings=settings, runner=runner)
        if not isinstance(outcome, WorkflowOutcome):
            raise TypeError(f"workflow returned {type(outcome).__name__}, not WorkflowOutcome")
    except Exception as exc:  # recorded as a failed attempt, never dropped
        outcome = None
        harness_error = f"{type(exc).__name__}: {exc}"[:500]
    latency = time.perf_counter() - start
    return build_record(
        record,
        arm,
        settings,
        outcome,
        harness_error,
        provider.take_calls(),
        latency,
        started_at,
        context,
        provider,
    )


def existing_attempts(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            done.add((row["case_id"], row["arm"]))
    return done


WARMUP_CODE = "def warm_up(flag):\n    if flag:\n        return 1\n    else:\n        return 2\n"


def warm_up(provider, runner, arms: list[str]) -> dict:
    """Pay one-time costs before any timed case, so they do not land on the first arm.

    The runner computes its isolation self-checks, and the provider serves one untimed
    refactoring request per adapter state the arms use (loading the model and adapter).
    The warm-up function is not a dataset or demonstration case; its outputs are not
    evaluated, only recorded in the run manifest.
    """
    from refactor_ai.contracts import ChatMessage
    from refactor_ai.evaluation.protocol import generation_settings
    from refactor_ai.task_format import build_refactor_messages

    report: dict = {"runner": None, "provider_calls": []}
    if runner is not None:
        start = time.perf_counter()
        info = runner.info()
        report["runner"] = {
            "enabled": info.enabled,
            "reason": info.reason,
            "elapsed_s": round(time.perf_counter() - start, 3),
        }
    adapter_states = sorted({ARM_SPECS[arm].refactor_use_adapter for arm in arms})
    messages = [ChatMessage(**m) for m in build_refactor_messages(WARMUP_CODE)]
    config = generation_settings()[Role.REFACTOR]
    for use_adapter in adapter_states:
        request = GenerationRequest(
            role=Role.REFACTOR, messages=messages, config=config, use_adapter=use_adapter
        )
        start = time.perf_counter()
        result = provider.generate(request)
        report["provider_calls"].append(
            {
                "use_adapter": use_adapter,
                "elapsed_s": round(time.perf_counter() - start, 3),
                "error": result.error.code.value if result.error else None,
                "model": result.model.model_dump(mode="json") if result.model else None,
            }
        )
    return report


def arm_order(index: int, arms: list[str]) -> list[str]:
    """Rotate the arm order from case to case so no arm always runs first."""
    shift = index % len(arms)
    return arms[shift:] + arms[:shift]


def run_evaluation(
    records: list[dict],
    arms: list[str],
    *,
    workflow: WorkflowFn,
    provider,
    runner,
    context: EvaluationContext,
    output_path: Path,
    resume: bool = False,
    progress: Callable[[EvaluationRecord], None] | None = None,
) -> dict:
    """Evaluate every case under every arm (case-major, rotated arm order); one line each."""
    if output_path.exists() and not resume:
        raise FileExistsError(f"{output_path} exists; use a new evaluation id or resume it")
    done = existing_attempts(output_path) if resume else set()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metered = provider if isinstance(provider, MeteredProvider) else MeteredProvider(provider)
    written: Counter = Counter()
    with output_path.open("a", encoding="utf-8", newline="\n") as handle:
        for index, record in enumerate(records):
            for position, arm in enumerate(arm_order(index, arms)):
                if (record["id"], arm) in done:
                    continue
                result = evaluate_case(
                    record, arm, workflow=workflow, provider=metered, runner=runner, context=context
                )
                result.order_position = position
                handle.write(result.model_dump_json() + "\n")
                handle.flush()
                written[arm] += 1
                if progress is not None:
                    progress(result)
    return {
        "written_by_arm": dict(sorted(written.items())),
        "skipped_existing": len(done),
        "output": str(output_path),
    }

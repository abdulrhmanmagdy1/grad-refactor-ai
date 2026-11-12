"""Multi-Agent Coordination Orchestrator (FR03, FR04, FR07, FR08, ADR10, Phase 3).

Orchestrates the Analysis -> Refactoring -> Review roles with a bounded
correction loop (at most one retry), strict FR08 resource ceilings, recorded
reasoning traces, software-metric snapshots, and SQLite state persistence.

Every step is persisted so the UI can replay exactly what each agent did:
the plan, the provider metadata, the sandbox verdicts, and the metric deltas.
"""

import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from agents.analysis_agent import AnalysisAgent
from agents.refactoring_agent import RefactoringAgent
from agents.review_agent import ReviewAgent
from core.ast_analyzer import analyze
from core.db import DatabaseManager, db
from core.exceptions import (
    ExecutionTimeoutError,
    ModelInferenceError,
    ProviderUnavailableError,
)
from core.schemas import (
    AgentTrace,
    CreateRunRequest,
    DiffOutput,
    RunRecord,
    RunStatus,
    VerificationResult,
)
from models.base import BaseModelProvider
from models.mock_provider import MockModelProvider
from models.registry import create_provider

# Deterministic mapping from detector rule to the supported refactoring type (FR03).
RULE_TO_REFACTORING_TYPE: dict[str, str] = {
    "long-function": "extract-function",
    "deep-nesting": "flatten-nesting",
    "high-complexity": "simplify-conditionals",
    "high-cognitive-complexity": "simplify-conditionals",
    "long-parameter-list": "introduce-parameter-object",
    "mutable-default-arg": "normalise-mutable-defaults",
    "broad-exception-catch": "narrow-exception-handling",
    "dead-code-or-unused": "remove-dead-code",
    "duplicate-code-blocks": "extract-shared-helper",
}

_PROVIDER_FAILURES = (ProviderUnavailableError, ModelInferenceError, ExecutionTimeoutError)

_TRACE_METRIC_KEYS = (
    "loc",
    "functions_count",
    "classes_count",
    "total_cyclomatic_complexity",
    "max_cyclomatic_complexity",
    "cognitive_complexity_total",
    "max_cognitive_complexity",
    "maintainability_index",
)


def derive_refactoring_type(requested: str | None, findings: list[Any]) -> str:
    """Resolve the supported refactoring type returned for a run (FR03)."""
    if requested:
        return requested
    for finding in findings:
        mapped = RULE_TO_REFACTORING_TYPE.get(getattr(finding, "rule", ""))
        if mapped:
            return mapped
    return "general-cleanup"


def _metric_snapshot(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: metrics[key] for key in _TRACE_METRIC_KEYS if key in metrics}


def _env_int(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to a default."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class WorkflowOrchestrator:
    """Coordinates the Multi-Agent Refactoring workflow with deterministic guardrails."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
        default_provider: BaseModelProvider | None = None,
        max_retries: int = 1,
        analysis_agent: AnalysisAgent | None = None,
        review_agent: ReviewAgent | None = None,
        max_concurrent_runs: int | None = None,
    ) -> None:
        self.db = database or db
        self.default_provider = default_provider or MockModelProvider()
        self.max_retries = min(1, max(0, max_retries))  # Strictly bounded to at most 1
        self.analysis_agent = analysis_agent or AnalysisAgent()
        self.review_agent = review_agent or ReviewAgent()
        # Guard against a local user starting more workflows than the machine
        # can serve; the API answers 429 instead of piling up background work.
        self.max_concurrent_runs = (
            max_concurrent_runs
            if max_concurrent_runs is not None
            else _env_int("REFACTOR_AI_MAX_CONCURRENT_RUNS", 2)
        )
        self._active_runs: set[str] = set()

    @property
    def active_runs(self) -> int:
        """Number of workflows currently executing."""
        return len(self._active_runs)

    def has_capacity(self) -> bool:
        """Whether another workflow may be started right now."""
        return self.active_runs < self.max_concurrent_runs

    def _resolve_provider(self, provider_name: str | None) -> BaseModelProvider:
        """Resolve the requested provider through the provider registry (Phase 2/6)."""
        return create_provider(provider_name, default=self.default_provider)

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    async def execute_run(self, request: CreateRunRequest, run_id: str | None = None) -> RunRecord:
        """Execute the end-to-end multi-agent refactoring workflow."""
        run_id = run_id or str(uuid.uuid4())
        now_iso = datetime.now(UTC).isoformat()

        self._active_runs.add(run_id)
        record = RunRecord(
            id=run_id,
            created_at=now_iso,
            status=RunStatus.QUEUED,
            input_code=request.code,
            refactoring_type=request.refactoring_type,
            metrics={
                "max_retries_allowed": self.max_retries,
                "limits": {
                    "max_model_calls": request.max_model_calls,
                    "max_total_tokens": request.max_total_tokens,
                    "max_duration_seconds": request.max_duration_seconds,
                    "max_retries": self.max_retries,
                },
            },
            findings=[],
        )
        self.db.create_run(record)

        start_time = time.perf_counter()
        traces: list[AgentTrace] = []

        try:
            return await self._run_workflow(record, request, traces, start_time)
        except Exception as exc:  # noqa: BLE001 - runs must fail with a recorded reason
            record.status = RunStatus.FAILED
            record.errors = f"Workflow execution error: {exc}"
            record.agent_traces = traces
            record.metrics["total_duration_ms"] = round(
                (time.perf_counter() - start_time) * 1000, 2
            )
            self.db.update_run(record)
            return record
        finally:
            self._active_runs.discard(run_id)

    # ------------------------------------------------------------------ #
    # Workflow
    # ------------------------------------------------------------------ #
    async def _run_workflow(
        self,
        record: RunRecord,
        request: CreateRunRequest,
        traces: list[AgentTrace],
        start_time: float,
    ) -> RunRecord:
        timing: dict[str, Any] = {}
        refactor_agent = RefactoringAgent(self._resolve_provider(request.provider))

        # ---- Step 1: Analysis (AST-only; never executes code, NFR01) ----
        record.status = RunStatus.ANALYZING
        self.db.update_run(record)
        t0 = time.perf_counter()
        analysis_res = await self.analysis_agent.analyze(request.code)
        analysis_ms = round((time.perf_counter() - t0) * 1000, 2)
        timing["analysis_ms"] = analysis_ms

        if not analysis_res.syntax_valid:
            traces.append(
                AgentTrace(
                    agent="analysis",
                    phase="analyze",
                    summary="Input rejected: the submitted code does not parse.",
                    details={"error": analysis_res.error},
                    duration_ms=analysis_ms,
                )
            )
            record.status = RunStatus.FAILED
            record.errors = f"Input code rejected: {analysis_res.error}"
            record.agent_traces = traces
            record.metrics.update(timing)
            record.metrics["total_duration_ms"] = round(
                (time.perf_counter() - start_time) * 1000, 2
            )
            self.db.update_run(record)
            return record

        record.findings = analysis_res.findings
        record.refactoring_type = derive_refactoring_type(request.refactoring_type, record.findings)
        record.metrics_before = analysis_res.metrics
        record.metrics["ast_metrics"] = analysis_res.metrics
        record.ast_graph_before = analysis_res.ast_graph

        plan = self.analysis_agent.build_plan(request.code, analysis_res)
        rule_counts: dict[str, int] = {}
        for finding in analysis_res.findings:
            rule_counts[finding.rule] = rule_counts.get(finding.rule, 0) + 1
        traces.append(
            AgentTrace(
                agent="analysis",
                phase="plan",
                summary=self.analysis_agent.formulate_goal(analysis_res.findings),
                details={
                    "engine": analysis_res.engine,
                    "finding_count": len(analysis_res.findings),
                    "finding_rules": rule_counts,
                    "metrics": _metric_snapshot(analysis_res.metrics),
                    "plan": plan.model_dump(),
                },
                duration_ms=analysis_ms,
            )
        )

        # ---- Steps 2-4: Generation + Review with the bounded correction loop ----
        candidate_code = ""
        diff_output: DiffOutput | None = None
        verification: VerificationResult | None = None
        explanation = ""
        gen_metadata: dict[str, Any] = {}
        retries_used = 0
        retry_feedback: str | None = None
        model_calls = 0
        total_tokens = 0
        abort_reason: str | None = None
        auto_test_source: str | None = None

        max_allowed_attempts = 1 + self.max_retries  # initial attempt + at most 1 retry

        for attempt in range(max_allowed_attempts):
            # FR08: enforce declared wall-clock, call, and token ceilings.
            elapsed = time.perf_counter() - start_time
            if elapsed > request.max_duration_seconds:
                abort_reason = (
                    f"Elapsed-time limit of {request.max_duration_seconds}s exceeded "
                    f"(FR08); aborted after {round(elapsed, 2)}s."
                )
                break
            if model_calls >= request.max_model_calls:
                abort_reason = (
                    f"Model call limit of {request.max_model_calls} reached before "
                    f"attempt {attempt + 1} (FR08)."
                )
                break

            record.status = RunStatus.GENERATING
            self.db.update_run(record)

            t_gen = time.perf_counter()
            try:
                candidate_code, gen_metadata = await refactor_agent.refactor(
                    code=request.code,
                    findings=record.findings,
                    retry_feedback=retry_feedback,
                    options={
                        "provider": request.provider,
                        "analysis_plan": plan.model_dump(),
                        "review_critique": retry_feedback,
                    },
                )
            except _PROVIDER_FAILURES as exc:
                generation_ms = round((time.perf_counter() - t_gen) * 1000, 2)
                timing[f"generation_attempt_{attempt + 1}_ms"] = generation_ms
                traces.append(
                    AgentTrace(
                        agent="refactoring",
                        phase="generate",
                        summary=f"Attempt {attempt + 1} failed: {exc}",
                        details={
                            "attempt": attempt + 1,
                            "provider": request.provider,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                        duration_ms=generation_ms,
                    )
                )
                abort_reason = f"Model provider failure: {exc}"
                break

            model_calls += 1
            timing[f"generation_attempt_{attempt + 1}_ms"] = round(
                (time.perf_counter() - t_gen) * 1000, 2
            )
            traces.append(
                AgentTrace(
                    agent="refactoring",
                    phase="generate",
                    summary=(
                        f"Attempt {attempt + 1}: generated a candidate "
                        f"({len(candidate_code.splitlines())} lines) via provider "
                        f"'{gen_metadata.get('provider', request.provider)}'."
                    ),
                    details={
                        "attempt": attempt + 1,
                        "is_retry": bool(retry_feedback),
                        "provider": gen_metadata.get("provider", request.provider),
                        "model": gen_metadata.get("model"),
                        "engine": gen_metadata.get("engine"),
                        "resolution": gen_metadata.get("resolution"),
                        "transformations": gen_metadata.get("transformations", []),
                        "tokens": {
                            "prompt_tokens": gen_metadata.get("prompt_tokens", 0),
                            "completion_tokens": gen_metadata.get("completion_tokens", 0),
                            "total_tokens": gen_metadata.get("total_tokens", 0),
                        },
                    },
                    duration_ms=timing[f"generation_attempt_{attempt + 1}_ms"],
                )
            )

            total_tokens += int(gen_metadata.get("total_tokens", 0) or 0)
            if total_tokens > request.max_total_tokens:
                abort_reason = (
                    f"Generated-token limit of {request.max_total_tokens} exceeded "
                    f"({total_tokens} tokens) (FR08)."
                )
                break

            record.status = RunStatus.VERIFYING
            self.db.update_run(record)

            t_ver = time.perf_counter()
            verification, diff_output, attempt_auto_tests = self.review_agent.review(
                original_code=request.code,
                candidate_code=candidate_code,
                test_code=request.test_code,
                findings=record.findings,
            )
            if attempt_auto_tests is not None:
                auto_test_source = attempt_auto_tests
            verification_ms = round((time.perf_counter() - t_ver) * 1000, 2)
            timing[f"verification_attempt_{attempt + 1}_ms"] = verification_ms
            traces.append(
                AgentTrace(
                    agent="review",
                    phase="review",
                    summary=(
                        f"Attempt {attempt + 1}: verdict '{verification.review_verdict}' - "
                        f"{verification.review_notes}"
                    )[:500],
                    details={
                        "attempt": attempt + 1,
                        "verdict": verification.review_verdict,
                        "syntax_valid": verification.syntax_valid,
                        "preserved_symbols": verification.preserved_symbols,
                        "signature_violations": verification.details.get(
                            "signature_violations", []
                        ),
                        "tests_available": verification.tests_available,
                        "tests_passed": verification.tests_passed,
                        "auto_generated_tests": verification.auto_generated_tests,
                        "resolved_findings": verification.details.get("resolved_findings", []),
                        "remaining_findings": verification.details.get("remaining_findings", []),
                        "metrics_delta": verification.metrics_delta,
                        "critique": verification.critique_feedback,
                    },
                    duration_ms=verification_ms,
                )
            )

            if verification.review_verdict in ("approved", "uncertain"):
                explanation = await refactor_agent.explain(
                    request.code, candidate_code, diff_output.diff
                )
                break

            if attempt < self.max_retries:
                retries_used += 1
                retry_feedback = verification.critique_feedback or (
                    f"Attempt {attempt + 1} failed review: {verification.review_notes}. "
                    "Ensure valid syntax and that all original symbols are preserved."
                )
            else:
                break

        # ---- Finalization and persistence ----
        total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        timing["total_duration_ms"] = total_duration_ms
        timing["retries_used"] = retries_used
        timing["tokens"] = {
            "prompt_tokens": gen_metadata.get("prompt_tokens", 0),
            "completion_tokens": gen_metadata.get("completion_tokens", 0),
            "total_tokens": gen_metadata.get("total_tokens", 0),
        }
        timing["model"] = gen_metadata.get("model", "unknown")
        timing["provider"] = gen_metadata.get("provider", request.provider)
        timing["model_calls"] = model_calls
        timing["generated_tokens_total"] = total_tokens

        record.metrics.update(timing)
        record.output_code = candidate_code
        record.diff = diff_output.diff if diff_output else None
        record.explanation = explanation
        record.verification = verification
        record.auto_generated_tests = auto_test_source
        record.agent_traces = traces

        if verification is not None:
            record.metrics_after = verification.metrics_after
            record.metrics_delta = verification.metrics_delta
            if verification.review_verdict in ("approved", "uncertain"):
                after_analysis = analyze(candidate_code)
                if after_analysis.syntax_valid:
                    record.ast_graph_after = after_analysis.ast_graph

        if abort_reason is not None:
            record.status = RunStatus.FAILED
            record.errors = abort_reason
        elif verification is not None and verification.review_verdict in (
            "approved",
            "uncertain",
        ):
            record.status = RunStatus.COMPLETED
        else:
            record.status = RunStatus.FAILED
            record.errors = verification.review_notes if verification else "Verification failed"

        self.db.update_run(record)
        return record


# Global orchestrator instance
orchestrator = WorkflowOrchestrator()

"""Workflow coordinator: validate, analyze, generate, verify, review, correct at most once.

run_workflow() implements docs/architecture/contracts.md and docs/architecture/workflow.md:

1. Validate deterministically (guard_clauses.check_input). Unsupported input completes
   with disposition no_change, reason codes and zero model calls; an expression nested
   too deeply for the reference rewrite counts as no_opportunity, with a warning.
2. Analyze (multi-role): one call; strict JSON with one deterministic repair; findings
   outside the input are dropped; unusable output falls back to the static findings.
3. Generate: one refactoring call (task_format's prompt, PROMPT_VERSION; multi-role adds
   analysis notes).
4. Verify: syntax (ast only), task rubric and trusted reference tests, kept separate.
5. Review (multi-role): one call; the verdict never overrides a failed check.
6. Correct once (multi-role): when a check fails, the review rejects or no code was
   produced, one corrected generation, its verification and one more review. If the
   provider refuses the correction prompt as input_too_long (it holds the code twice),
   the correction is skipped with a warning and the first proposal is reported.

Budgets: single-role makes exactly one call; multi-role at most settings.max_calls (five
by default) and settings.max_corrections (one). settings.run_timeout_s bounds the whole
run: it is checked before every model call and verification step, and each call's
timeout is the smaller of its role setting and the time left. Provider errors in any role
fail the run with the provider's error code (except input_too_long on the correction, see
above); unexpected exceptions become internal_error
without exception text in user-facing messages. The original code is never modified, and
the diff is computed by the application, never taken from a model.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from refactor_ai.agents import parsing, prompts
from refactor_ai.contracts import (
    AnalysisReport,
    AttemptRecord,
    ChatMessage,
    Disposition,
    GenerationConfig,
    GenerationRequest,
    GenerationResult,
    ModelReference,
    ModelReviewResult,
    ProviderError,
    ProviderErrorCode,
    ProviderMode,
    ReferenceRunner,
    ReferenceTestsResult,
    Role,
    RoleFinding,
    RunError,
    RunStatus,
    StageTiming,
    StatusCallback,
    WorkflowMode,
    WorkflowOutcome,
    WorkflowRequest,
    WorkflowSettings,
)
from refactor_ai.providers.base import Provider
from refactor_ai.task_format import parse_refactor_output
from refactor_ai.tasks import guard_clauses
from refactor_ai.verification import checks as verification_checks
from refactor_ai.verification import disposition
from refactor_ai.verification.diffing import changed_lines, source_lines, unified_diff
from refactor_ai.verification.registry import code_matches_case

logger = logging.getLogger(__name__)

# --- Stop reasons (WorkflowOutcome.stop_reason) ----------------------------------------
# Completed runs.
STOP_UNSUPPORTED_INPUT = "unsupported_input"  # validation rejected the input; zero calls
STOP_SINGLE_ROLE_COMPLETE = "single_role_complete"  # the one generation was verified
STOP_NO_CORRECTION_NEEDED = "no_correction_needed"  # nothing failed and no rejection
STOP_CORRECTION_USED = "correction_used"  # the single correction was made and verified
STOP_CORRECTION_DISABLED = "correction_disabled"  # needed, but max_corrections is 0
STOP_CALL_BUDGET_EXHAUSTED = "call_budget_exhausted"  # needed, but < 2 calls were left
STOP_CORRECTION_INPUT_TOO_LONG = "correction_input_too_long"  # correction prompt refused
# Failed runs (WorkflowOutcome.error is set).
STOP_PROVIDER_ERROR = "provider_error"
STOP_RUN_TIMEOUT = "run_timeout"
STOP_UNPARSEABLE_OUTPUT = "unparseable_output"
STOP_INVALID_SETTINGS = "invalid_settings"
STOP_REFERENCE_CASE_MISMATCH = "reference_case_mismatch"
STOP_INTERNAL_ERROR = "internal_error"

COMPLETED_STOP_REASONS = frozenset(
    {
        STOP_UNSUPPORTED_INPUT,
        STOP_SINGLE_ROLE_COMPLETE,
        STOP_NO_CORRECTION_NEEDED,
        STOP_CORRECTION_USED,
        STOP_CORRECTION_DISABLED,
        STOP_CALL_BUDGET_EXHAUSTED,
        STOP_CORRECTION_INPUT_TOO_LONG,
    }
)
FAILED_STOP_REASONS = frozenset(
    {
        STOP_PROVIDER_ERROR,
        STOP_RUN_TIMEOUT,
        STOP_UNPARSEABLE_OUTPUT,
        STOP_INVALID_SETTINGS,
        STOP_REFERENCE_CASE_MISMATCH,
        STOP_INTERNAL_ERROR,
    }
)
STOP_REASONS = COMPLETED_STOP_REASONS | FAILED_STOP_REASONS

# RunError.code values besides the ProviderErrorCode values.
ERROR_RUN_TIMEOUT = "run_timeout"
ERROR_UNPARSEABLE_OUTPUT = "unparseable_output"
ERROR_INVALID_SETTINGS = "invalid_settings"
ERROR_REFERENCE_CASE_MISMATCH = "reference_case_mismatch"
ERROR_INTERNAL = "internal_error"

UNSUPPORTED_TASK_TYPE = "unsupported_task_type"
NO_OPPORTUNITY = "no_opportunity"  # guard_clauses' code when the rewrite cannot help
MIN_MULTI_ROLE_CALLS = 3  # analysis, generation, review
CORRECTION_CALLS = 2  # corrected generation and its review
MAX_STATIC_FINDINGS = parsing.MAX_FINDINGS
MAX_MESSAGE_CHARS = 300

FAKE_PROVIDER_WARNING = (
    "The fake provider produced these outputs; they are deterministic test fixtures, not "
    "language-model inference."
)
INTERNAL_ERROR_MESSAGE = "An internal error stopped the workflow; details were logged."
PARSE_ERROR_TEXT = {
    "empty_output": "the answer was empty",
    "no_code_block": "no fenced Python code block was found",
    "unterminated_code_block": "the Python code block was not closed (the answer may have "
    "been cut off)",
}


class CallRecord(BaseModel):
    """One provider call, with the exact model identity reported for it."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    role: Role
    attempt: int = Field(ge=0)
    prompt_version: str
    use_adapter: bool
    timeout_s: float
    model: ModelReference | None = None
    elapsed_s: float = Field(ge=0.0)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str
    error: ProviderError | None = None
    raw_output: str = ""
    parse_error: str | None = None
    parse_repaired: bool = False
    parse_repairs: list[str] = Field(default_factory=list)


class WorkflowTrace(BaseModel):
    """Details that WorkflowOutcome (schema version 1) has no field for."""

    model_config = ConfigDict(extra="forbid")

    calls: list[CallRecord] = Field(default_factory=list)
    statuses: list[RunStatus] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(
        default_factory=lambda: {
            "analysis": prompts.ANALYSIS_PROMPT_VERSION,
            "refactor": prompts.REFACTOR_PROMPT_VERSION,
            "correction": prompts.CORRECTION_PROMPT_VERSION,
            "review": prompts.REVIEW_PROMPT_VERSION,
        }
    )


class _RunFailed(Exception):
    def __init__(self, code: str, message: str, stage: str, stop_reason: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.stop_reason = stop_reason


def _sanitize(message: str) -> str:
    """First line of a provider message, bounded; tracebacks never reach users."""
    lines = [line.strip() for line in str(message).splitlines() if line.strip()]
    text = lines[0] if lines else "The provider reported an error without details."
    if text.startswith("Traceback"):
        text = "The provider reported an internal error."
    return text if len(text) <= MAX_MESSAGE_CHARS else text[: MAX_MESSAGE_CHARS - 3] + "..."


class _Workflow:
    def __init__(
        self,
        request: WorkflowRequest,
        provider: Provider,
        settings: WorkflowSettings,
        runner: ReferenceRunner | None,
        on_status: StatusCallback | None,
    ) -> None:
        self.request = request
        self.code = request.code
        self.provider = provider
        self.settings = settings
        self.runner = runner
        self.on_status = on_status
        self.multi = settings.mode == WorkflowMode.MULTI_ROLE
        self.max_calls = settings.max_calls if self.multi else 1
        self.deadline = time.perf_counter() + settings.run_timeout_s
        self.trace = WorkflowTrace()
        self.attempts: list[AttemptRecord] = []
        self.checks: dict[int, verification_checks.DeterministicChecks] = {}
        self.timings: list[StageTiming] = []
        self.warnings: list[str] = []
        self.analysis: AnalysisReport | None = None
        self.findings: list[RoleFinding] = []
        self.last_model: ModelReference | None = None
        self.stage = "validation"

    # --- Driver -----------------------------------------------------------------------

    def execute(self) -> tuple[WorkflowOutcome, WorkflowTrace]:
        try:
            outcome = self._run()
        except _RunFailed as failure:
            outcome = self._failed(failure)
        except Exception:
            logger.exception("The workflow stopped with an unexpected error")
            internal = _RunFailed(
                ERROR_INTERNAL, INTERNAL_ERROR_MESSAGE, self.stage, STOP_INTERNAL_ERROR
            )
            try:
                outcome = self._failed(internal)
            except Exception:
                logger.exception("The failed outcome could not be assembled")
                outcome = self._minimal_failure(internal)
        self._set_status(outcome.status)
        outcome = outcome.model_copy(update={"warnings": list(self.warnings)})
        return outcome, self.trace

    def _run(self) -> WorkflowOutcome:
        if self.provider.mode == ProviderMode.FAKE:
            self._warn(FAKE_PROVIDER_WARNING)
        with self._stage("validation", 0):
            reasons, check = self._validate()
        if reasons:
            return self._no_change(reasons)
        if self.multi:
            self._analyze(check)
        first = self._attempt(
            0, prompts.build_refactor_request(self.code, self._notes()), "refactor"
        )
        if not self.multi:
            stop = STOP_SINGLE_ROLE_COMPLETE
        elif not self._needs_correction(first):
            stop = STOP_NO_CORRECTION_NEEDED
        elif self.settings.max_corrections < 1:
            stop = STOP_CORRECTION_DISABLED
            self._warn("A correction was needed, but max_corrections is 0.")
        elif self.max_calls - len(self.trace.calls) < CORRECTION_CALLS:
            stop = STOP_CALL_BUDGET_EXHAUSTED
            self._warn(
                f"A correction was needed, but only {self.max_calls - len(self.trace.calls)} "
                f"of max_calls={self.max_calls} calls were left (a correction needs two)."
            )
        else:
            messages = prompts.build_correction_messages(
                self.code, self.findings, first.proposed_code, self._problems(first)
            )
            stop = self._correct(messages)
        final = next(
            (item for item in reversed(self.attempts) if item.proposed_code is not None), None
        )
        if final is None:
            errors = [item.parse_error for item in self.attempts if item.parse_error]
            error = errors[-1] if errors else "unknown"
            text = PARSE_ERROR_TEXT.get(error, error)
            raise _RunFailed(
                ERROR_UNPARSEABLE_OUTPUT,
                f"The refactoring output could not be parsed: {text}.",
                "generation",
                STOP_UNPARSEABLE_OUTPUT,
            )
        if stop == STOP_CORRECTION_USED and final is not self.attempts[-1]:
            self._warn(
                "The correction produced no parseable code; the first proposal and its "
                "verification are reported."
            )
        return self._completed(final, stop)

    def _correct(self, messages: list[ChatMessage]) -> str:
        """The single correction. The correction prompt holds the code twice, so it is the
        one prompt that can exceed the refactoring role's max_input_tokens when the first
        prompt fit. The provider checks the limit exactly, before generating; a refusal
        skips the correction instead of failing the run. Any other error still fails it."""
        try:
            self._attempt(1, messages, "correction")
        except _RunFailed as failure:
            # Only the corrected generation may be skipped; the review of a corrected
            # proposal (stage "review") and every other error still fail the run.
            refused = failure.code == ProviderErrorCode.INPUT_TOO_LONG.value
            if not refused or failure.stage != "generation":
                raise
            self._warn(
                "The correction prompt exceeded the refactoring role's input limit "
                f"({failure.message}); the correction was skipped and the first proposal is "
                "reported."
            )
            self._set_status(RunStatus.VERIFYING)
            return STOP_CORRECTION_INPUT_TOO_LONG
        return STOP_CORRECTION_USED

    # --- Steps ------------------------------------------------------------------------

    def _validate(self) -> tuple[list[str], guard_clauses.InputCheck | None]:
        settings = self.settings
        if self.multi and settings.max_calls < MIN_MULTI_ROLE_CALLS:
            raise _RunFailed(
                ERROR_INVALID_SETTINGS,
                f"Multi-role runs need max_calls of at least {MIN_MULTI_ROLE_CALLS} (analysis, "
                f"generation and review); got {settings.max_calls}.",
                "validation",
                STOP_INVALID_SETTINGS,
            )
        case = self.request.reference_case
        if case is not None and (
            case.task_type != self.request.task_type or not code_matches_case(self.code, case)
        ):
            raise _RunFailed(
                ERROR_REFERENCE_CASE_MISMATCH,
                "The selected reference case does not match the submitted code.",
                "validation",
                STOP_REFERENCE_CASE_MISMATCH,
            )
        if self.request.task_type != guard_clauses.TASK_TYPE:
            return [UNSUPPORTED_TASK_TYPE], None
        try:
            check = guard_clauses.check_input(self.code)
        except (RecursionError, MemoryError):
            # check_input applies the reference rewrite with recursive ast helpers. Valid
            # code inside the size limits can nest an expression deeper than they allow
            # (for example a long a + b + ... chain); the rewrite then cannot be computed,
            # so it cannot lower the nesting depth (task scope rule 5).
            self._warn(
                "The deterministic guard-clause rewrite could not be computed because an "
                "expression in the code is nested too deeply."
            )
            return [NO_OPPORTUNITY], None
        if not check.supported:
            return list(check.reasons), check
        if "```" in self.code:
            self._warn(
                "The code contains a Markdown fence (```), which can make the fenced code in "
                "model prompts ambiguous."
            )
        return [], check

    def _analyze(self, check: guard_clauses.InputCheck | None) -> None:
        self._check_deadline("analysis")
        self._set_status(RunStatus.ANALYZING)
        with self._stage("analysis", 0):
            result, record = self._call(
                Role.ANALYSIS,
                0,
                prompts.build_analysis_messages(self.code),
                prompts.ANALYSIS_PROMPT_VERSION,
                use_adapter=False,
            )
        parsed = parsing.parse_analysis(result.text, len(source_lines(self.code)))
        record.parse_error = parsed.error
        record.parse_repaired = parsed.repaired
        record.parse_repairs = list(parsed.repairs)
        if parsed.repaired:
            self._warn(f"analysis: the JSON output was repaired ({', '.join(parsed.repairs)}).")
        for problem in parsed.dropped:
            self._warn(f"analysis: {problem}; the finding was dropped.")
        report = parsed.report
        problem = None
        if report is None:
            problem = f"the output could not be parsed ({parsed.error})"
        elif not report.supported_task:
            problem = "the model reported the input as unsupported, but validation found a case"
        elif not report.findings:
            problem = "the output contained no valid finding"
        if problem is not None:
            self._warn(
                f"analysis: {problem}; the deterministic findings were used (source=static)."
            )
            report = AnalysisReport(
                supported_task=True,
                findings=self._static_findings(check),
                unsupported_reason=None,
                source="static",
            )
        self.analysis = report
        self.findings = list(report.findings)

    def _attempt(self, index: int, messages: list[ChatMessage], kind: str) -> AttemptRecord:
        self._check_deadline("generation")
        self._set_status(RunStatus.GENERATING)
        version = (
            prompts.CORRECTION_PROMPT_VERSION
            if kind == "correction"
            else prompts.REFACTOR_PROMPT_VERSION
        )
        calls_before = len(self.trace.calls)
        try:
            with self._stage("generation", index):
                result, record = self._call(
                    Role.REFACTOR,
                    index,
                    messages,
                    version,
                    use_adapter=self.settings.refactor_use_adapter,
                )
        except Exception:
            if len(self.trace.calls) > calls_before:  # the call was made and failed
                failed = self.trace.calls[-1]
                self.attempts.append(
                    AttemptRecord(
                        attempt=index,
                        raw_output=failed.raw_output or None,
                        model=failed.model,
                        prompt_tokens=failed.prompt_tokens,
                        completion_tokens=failed.completion_tokens,
                        elapsed_s=failed.elapsed_s,
                    )
                )
            raise
        parsed = parse_refactor_output(result.text)
        record.parse_error = parsed.error
        record.parse_repaired = parsed.repaired
        record.parse_repairs = list(parsed.notes)
        attempt = AttemptRecord(
            attempt=index,
            raw_output=result.text,
            parse_error=parsed.error,
            parse_repaired=parsed.repaired,
            proposed_code=parsed.code,
            explanation=parsed.explanation,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            elapsed_s=record.elapsed_s,
        )
        self.attempts.append(attempt)
        if parsed.repaired:
            self._warn(
                f"refactor attempt {index}: the output was repaired ({', '.join(parsed.notes)})."
            )
        self._set_status(RunStatus.VERIFYING)
        if parsed.code is None:
            text = PARSE_ERROR_TEXT.get(parsed.error or "", parsed.error or "unknown")
            self._warn(
                f"refactor attempt {index}: the output could not be parsed ({parsed.error})."
            )
            with self._stage("verification", index):
                attempt.verification = disposition.not_run_verification(
                    Disposition.FAILED,
                    [
                        disposition.reason(
                            ERROR_UNPARSEABLE_OUTPUT,
                            f"The refactoring output could not be parsed: {text}.",
                        )
                    ],
                )
            return attempt

        with self._stage("verification", index):
            remaining = self._check_deadline("verification")
            deterministic = verification_checks.run_checks(
                self.code,
                parsed.code,
                case=self.request.reference_case,
                runner=self.runner,
                timeout_s=remaining,
            )
        self.checks[index] = deterministic
        review = ModelReviewResult(status="not_run")
        if self.multi:
            self._check_deadline("review")
            with self._stage("review", index):
                result, record = self._call(
                    Role.REVIEW,
                    index,
                    prompts.build_review_messages(
                        self.code, parsed.code, verification_checks.describe_checks(deterministic)
                    ),
                    prompts.REVIEW_PROMPT_VERSION,
                    use_adapter=False,
                )
            parsed_review = parsing.parse_review(result.text)
            record.parse_error = parsed_review.error
            record.parse_repaired = parsed_review.repaired
            record.parse_repairs = list(parsed_review.repairs)
            if parsed_review.repaired:
                self._warn(
                    f"review attempt {index}: the JSON output was repaired "
                    f"({', '.join(parsed_review.repairs)})."
                )
            if parsed_review.result is not None:
                attempt.review = parsed_review.result
                review = ModelReviewResult(
                    status=parsed_review.result.verdict.value,
                    reasons=list(parsed_review.result.reasons),
                )
            else:
                self._warn(
                    f"review attempt {index}: the output could not be parsed "
                    f"({parsed_review.error}); the review is recorded as an error."
                )
                review = ModelReviewResult(
                    status="error",
                    error=f"The review output could not be parsed: {parsed_review.error}.",
                )
        attempt.verification = disposition.verification_result(
            deterministic.syntax,
            deterministic.rubric,
            deterministic.tests,
            review,
            mode=self.settings.mode,
        )
        return attempt

    def _call(
        self,
        role: Role,
        attempt: int,
        messages: list[ChatMessage],
        prompt_version: str,
        *,
        use_adapter: bool,
    ) -> tuple[GenerationResult, CallRecord]:
        if len(self.trace.calls) >= self.max_calls:
            raise RuntimeError("The workflow attempted a call beyond its budget")
        remaining = self._check_deadline(self.stage)
        config = self._config(role)
        timeout = min(config.timeout_s, remaining)
        capped = remaining < config.timeout_s
        request = GenerationRequest(
            role=role,
            messages=messages,
            config=GenerationConfig(**{**config.model_dump(), "timeout_s": timeout}),
            use_adapter=use_adapter,
        )
        started = time.perf_counter()
        try:
            result = self.provider.generate(request)
            if not isinstance(result, GenerationResult):
                raise TypeError(f"The provider returned {type(result).__name__}")
        except Exception as exc:
            # A provider must not raise; count the call, then fail as internal_error.
            self.trace.calls.append(
                CallRecord(
                    index=len(self.trace.calls),
                    role=role,
                    attempt=attempt,
                    prompt_version=prompt_version,
                    use_adapter=use_adapter,
                    timeout_s=timeout,
                    elapsed_s=time.perf_counter() - started,
                    finish_reason="error",
                    error=ProviderError(
                        code=ProviderErrorCode.GENERATION_ERROR,
                        message=f"The provider raised {type(exc).__name__}.",
                    ),
                )
            )
            raise
        elapsed = time.perf_counter() - started
        record = CallRecord(
            index=len(self.trace.calls),
            role=role,
            attempt=attempt,
            prompt_version=prompt_version,
            use_adapter=use_adapter,
            timeout_s=timeout,
            model=result.model,
            elapsed_s=elapsed,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            finish_reason=result.finish_reason,
            error=result.error,
            raw_output=result.text,
        )
        self.trace.calls.append(record)
        if result.model is not None:
            self.last_model = result.model
        for warning in result.warnings:
            self._warn(f"{role.value} call: {warning}")
        if result.error is not None or result.finish_reason == "error":
            code = result.error.code if result.error else ProviderErrorCode.GENERATION_ERROR
            message = _sanitize(result.error.message if result.error else "")
            if code == ProviderErrorCode.TIMEOUT and capped:
                raise _RunFailed(
                    ERROR_RUN_TIMEOUT,
                    f"The run reached its {self.settings.run_timeout_s:g} s time limit during "
                    f"the {role.value} call.",
                    self.stage,
                    STOP_RUN_TIMEOUT,
                )
            raise _RunFailed(code.value, message, self.stage, STOP_PROVIDER_ERROR)
        if result.model is None:
            self._warn(f"{role.value} call: the provider did not report the model identity.")
        elif result.model.use_adapter != use_adapter:
            raise _RunFailed(
                ProviderErrorCode.MODEL_LOAD_ERROR.value,
                f"The provider reported use_adapter={result.model.use_adapter} for a "
                f"{role.value} call that requested use_adapter={use_adapter}.",
                self.stage,
                STOP_PROVIDER_ERROR,
            )
        if result.finish_reason == "length":
            self._warn(f"{role.value} call {record.index}: the output reached the token limit.")
        return result, record

    # --- Outcomes ---------------------------------------------------------------------

    def _completed(self, final: AttemptRecord, stop: str) -> WorkflowOutcome:
        proposed = final.proposed_code or ""
        return WorkflowOutcome(
            status=RunStatus.COMPLETED,
            provider_mode=self.provider.mode,
            model=final.model or self.last_model,
            analysis=self.analysis,
            findings=list(self.findings),
            proposed_code=proposed,
            explanation=final.explanation,
            diff=unified_diff(self.code, proposed),
            changed_lines=changed_lines(self.code, proposed),
            review=final.review,
            verification=final.verification,
            attempts=list(self.attempts),
            attempt_count=len(self.attempts),
            call_count=len(self.trace.calls),
            stage_timings=list(self.timings),
            stop_reason=stop,
        )

    def _no_change(self, codes: list[str]) -> WorkflowOutcome:
        texts = [
            "Only the guard_clauses task is supported."
            if code == UNSUPPORTED_TASK_TYPE
            else guard_clauses.reason_text(code)
            for code in codes
        ]
        return WorkflowOutcome(
            status=RunStatus.COMPLETED,
            provider_mode=self.provider.mode,
            analysis=AnalysisReport(
                supported_task=False,
                findings=[],
                unsupported_reason=" ".join(texts),
                source="static",
            ),
            verification=disposition.not_run_verification(
                Disposition.NO_CHANGE,
                [disposition.reason(code, text) for code, text in zip(codes, texts, strict=True)],
            ),
            stage_timings=list(self.timings),
            stop_reason=STOP_UNSUPPORTED_INPUT,
        )

    def _failed(self, failure: _RunFailed) -> WorkflowOutcome:
        syntax = rubric = tests = review = None
        latest = self.attempts[-1] if self.attempts else None
        if failure.stage == "review" and latest is not None and latest.attempt in self.checks:
            deterministic = self.checks[latest.attempt]
            syntax, rubric, tests = deterministic.syntax, deterministic.rubric, deterministic.tests
            review = ModelReviewResult(status="error", error=failure.message)
        elif failure.stage == "verification":
            tests = ReferenceTestsResult(status="not_run", reason=failure.message)
        verification = disposition.not_run_verification(
            Disposition.FAILED,
            [disposition.reason(failure.code, failure.message)],
            syntax=syntax,
            rubric=rubric,
            tests=tests,
            review=review,
        )
        if latest is not None and latest.proposed_code is not None and latest.verification is None:
            # The run stopped while this proposal was being verified or reviewed.
            latest.verification = verification
        return WorkflowOutcome(
            status=RunStatus.FAILED,
            provider_mode=self.provider.mode,
            model=(latest.model if latest is not None and latest.model else self.last_model),
            analysis=self.analysis,
            findings=list(self.findings),
            verification=verification,
            attempts=list(self.attempts),
            attempt_count=len(self.attempts),
            call_count=len(self.trace.calls),
            stage_timings=list(self.timings),
            stop_reason=failure.stop_reason,
            error=RunError(code=failure.code, message=failure.message, stage=failure.stage),
        )

    def _minimal_failure(self, failure: _RunFailed) -> WorkflowOutcome:
        """Last-resort failed outcome that depends on no intermediate state."""
        return WorkflowOutcome(
            status=RunStatus.FAILED,
            provider_mode=self.provider.mode,
            verification=disposition.not_run_verification(
                Disposition.FAILED, [disposition.reason(failure.code, failure.message)]
            ),
            call_count=len(self.trace.calls),
            stop_reason=failure.stop_reason,
            error=RunError(code=failure.code, message=failure.message, stage=failure.stage),
        )

    # --- Helpers ----------------------------------------------------------------------

    def _notes(self) -> list[RoleFinding] | None:
        return self.findings if self.multi else None

    def _static_findings(self, check: guard_clauses.InputCheck | None) -> list[RoleFinding]:
        opportunities = check.opportunities if check is not None else []
        return [
            RoleFinding(
                type=guard_clauses.FINDING_TYPE,
                start_line=item.start_line,
                end_line=item.end_line,
                reason=item.reason[:600],
            )
            for item in opportunities[:MAX_STATIC_FINDINGS]
        ]

    def _config(self, role: Role) -> GenerationConfig:
        config = self.settings.generation.get(role)
        if config is None:
            self._warn(f"No generation settings for the {role.value} role; defaults were used.")
            config = GenerationConfig()
        return config

    @staticmethod
    def _needs_correction(attempt: AttemptRecord) -> bool:
        if attempt.proposed_code is None or attempt.verification is None:
            return True
        result = attempt.verification
        return (
            result.syntax.status == "fail"
            or result.rubric.status == "fail"
            or result.reference_tests.status in ("fail", "error")
            or result.model_review.status == "reject"
        )

    @staticmethod
    def _problems(attempt: AttemptRecord) -> list[str]:
        """Concrete feedback on the previous attempt for the correction prompt."""
        if attempt.proposed_code is None or attempt.verification is None:
            text = PARSE_ERROR_TEXT.get(attempt.parse_error or "", "the answer could not be used")
            return [f"The answer could not be used: {text}."]
        result = attempt.verification
        problems: list[str] = []
        if result.syntax.status == "fail":
            problems.append(f"The code is not valid Python: {result.syntax.error}.")
        if result.rubric.status == "fail":
            problems += [f"Rubric: {text}" for text in result.rubric.reasons]
        tests = result.reference_tests
        if tests.status in ("fail", "error"):
            if tests.total:
                problems.append(f"Reference tests: {tests.passed or 0} of {tests.total} passed.")
            elif tests.reason:
                problems.append(f"Reference tests: {tests.reason}")
            problems += [
                f"Test {item.index} ({item.kind}): {item.detail}" for item in tests.failures[:3]
            ]
        if result.model_review.status == "reject":
            reasons = "; ".join(result.model_review.reasons) or "no reason was given"
            problems.append(f"The reviewer rejected the proposal: {reasons}")
            if attempt.review is not None and attempt.review.suggested_correction:
                problems.append(f"Reviewer suggestion: {attempt.review.suggested_correction}")
        return problems or ["The previous answer was not accepted."]

    def _check_deadline(self, stage: str) -> float:
        """Seconds left in the run (never more than run_timeout_s); raises when none."""
        remaining = min(self.settings.run_timeout_s, self.deadline - time.perf_counter())
        if remaining <= 0:
            raise _RunFailed(
                ERROR_RUN_TIMEOUT,
                f"The run reached its {self.settings.run_timeout_s:g} s time limit before the "
                f"{stage} step.",
                stage,
                STOP_RUN_TIMEOUT,
            )
        return remaining

    @contextmanager
    def _stage(self, name: str, attempt: int) -> Iterator[None]:
        self.stage = name
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        calls_before = len(self.trace.calls)
        try:
            yield
        finally:
            self.timings.append(
                StageTiming(
                    stage=name,
                    attempt=attempt,
                    started_at=started_at,
                    elapsed_s=max(0.0, time.perf_counter() - started),
                    calls=len(self.trace.calls) - calls_before,
                )
            )

    def _set_status(self, status: RunStatus) -> None:
        if self.trace.statuses and self.trace.statuses[-1] == status:
            return
        self.trace.statuses.append(status)
        if self.on_status is None:
            return
        try:
            self.on_status(status)
        except Exception:
            logger.exception("The status callback failed for status %s", status)
            self._warn(f"The status callback failed for status {status.value}; the run continued.")

    def _warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)


def run_workflow_traced(
    request: WorkflowRequest,
    *,
    provider: Provider,
    settings: WorkflowSettings,
    runner: ReferenceRunner | None = None,
    on_status: StatusCallback | None = None,
) -> tuple[WorkflowOutcome, WorkflowTrace]:
    """run_workflow plus the per-call trace (role, prompt version, model identity per
    call, raw output and parse outcome of every call)."""
    return _Workflow(request, provider, settings, runner, on_status).execute()


def run_workflow(
    request: WorkflowRequest,
    *,
    provider: Provider,
    settings: WorkflowSettings,
    runner: ReferenceRunner | None = None,
    on_status: StatusCallback | None = None,
) -> WorkflowOutcome:
    """Run the bounded refactoring workflow for one request; never raises for run errors."""
    outcome, _trace = run_workflow_traced(
        request, provider=provider, settings=settings, runner=runner, on_status=on_status
    )
    return outcome

"""Shared data contracts, schema version 1.

Every workstream (API, roles, provider, runner, evaluation, frontend) exchanges these
models. Changing a field requires updating docs/architecture/contracts.md, the example
JSON under docs/architecture/examples/ and the contract tests in the same change.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1
MAX_CODE_CHARS = 20000


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderMode(StrEnum):
    FAKE = "fake"
    LOCAL_MODEL = "local_model"


class Role(StrEnum):
    ANALYSIS = "analysis"
    REFACTOR = "refactor"
    REVIEW = "review"


class WorkflowMode(StrEnum):
    MULTI_ROLE = "multi_role"
    SINGLE_ROLE = "single_role"


class RunStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED})


class Disposition(StrEnum):
    PROPOSAL_READY = "proposal_ready"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"
    NO_CHANGE = "no_change"
    FAILED = "failed"


# --- Model provider -------------------------------------------------------------------


class ChatMessage(Contract):
    role: Literal["system", "user", "assistant"]
    content: str


class GenerationConfig(Contract):
    """Bounded generation settings. temperature 0 means greedy decoding."""

    max_new_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    seed: int = 42
    max_input_tokens: int = Field(default=2048, ge=1, le=32768)
    timeout_s: float = Field(default=120.0, gt=0.0, le=3600.0)


class ModelReference(Contract):
    """Exact identity of the weights that produced an output."""

    model_id: str
    model_revision: str
    adapter_id: str | None = None
    adapter_sha256: str | None = None
    use_adapter: bool = False


class ProviderErrorCode(StrEnum):
    TIMEOUT = "timeout"
    MODEL_LOAD_ERROR = "model_load_error"
    INPUT_TOO_LONG = "input_too_long"
    GENERATION_ERROR = "generation_error"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


class ProviderError(Contract):
    code: ProviderErrorCode
    message: str


class GenerationRequest(Contract):
    role: Role
    messages: list[ChatMessage] = Field(min_length=1)
    config: GenerationConfig = Field(default_factory=GenerationConfig)
    use_adapter: bool = False


class GenerationResult(Contract):
    """Providers return failures here instead of raising for expected problems."""

    text: str = ""
    provider_mode: ProviderMode
    model: ModelReference | None = None
    elapsed_s: float = Field(ge=0.0)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: Literal["stop", "length", "error"] = "stop"
    error: ProviderError | None = None
    warnings: list[str] = Field(default_factory=list)


class ProviderInfo(Contract):
    provider_mode: ProviderMode
    model_id: str | None = None
    model_revision: str | None = None
    adapter_id: str | None = None
    adapter_sha256: str | None = None
    device: str | None = None
    ready: bool = False
    detail: str | None = None


# --- Role outputs ---------------------------------------------------------------------


class RoleFinding(Contract):
    type: str = Field(min_length=1, max_length=64)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=600)

    @field_validator("end_line")
    @classmethod
    def end_after_start(cls, value: int, info) -> int:
        start = info.data.get("start_line")
        if start is not None and value < start:
            raise ValueError("end_line must not precede start_line")
        return value


class AnalysisReport(Contract):
    """Analysis-role output. source records whether a model or static rules produced it."""

    schema_version: int = SCHEMA_VERSION
    supported_task: bool
    findings: list[RoleFinding] = Field(default_factory=list, max_length=20)
    unsupported_reason: str | None = None
    source: Literal["model", "static"] = "model"


class RefactorProposal(Contract):
    schema_version: int = SCHEMA_VERSION
    task_type: str
    proposed_code: str | None = None
    explanation: str | None = None
    changed_lines: list[int] = Field(default_factory=list)
    error: str | None = None


class ReviewVerdict(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    UNCERTAIN = "uncertain"


class ReviewResult(Contract):
    schema_version: int = SCHEMA_VERSION
    verdict: ReviewVerdict
    reasons: list[str] = Field(default_factory=list, max_length=10)
    suggested_correction: str | None = None


# --- Trusted reference cases ----------------------------------------------------------


class ReferenceExpectation(Contract):
    """Expected outcome of one call. value is a Python literal (repr) for returns."""

    kind: Literal["return", "raise"]
    value: str | None = None
    exception: str | None = None


class ReferenceTest(Contract):
    """One trusted call. args/kwargs are Python literal source restored with literal_eval."""

    args: str = "[]"
    kwargs: str = "{}"
    expect: ReferenceExpectation


class ReferenceCase(Contract):
    """A server-owned trusted case. The runner never accepts caller-chosen paths or tests."""

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,95}$")
    task_type: str
    title: str | None = None
    function_name: str
    original_code: str
    reference_code: str | None = None
    tests: list[ReferenceTest] = Field(default_factory=list)
    source_group: str | None = None
    license: str | None = None
    provenance: str | None = None


# --- Verification ---------------------------------------------------------------------


class SyntaxCheck(Contract):
    status: Literal["pass", "fail", "not_run"]
    error: str | None = None


class RubricCheck(Contract):
    status: Literal["pass", "fail", "not_run"]
    checks: dict[str, bool] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class ReferenceTestFailure(Contract):
    index: int = Field(ge=0)
    kind: Literal[
        "wrong_value",
        "wrong_exception",
        "unexpected_exception",
        "missing_exception",
        "timeout",
        "missing_function",
        "runner_error",
    ]
    detail: str = Field(max_length=500)


class ReferenceTestsResult(Contract):
    """Reference-test outcome. not_available/not_run/error are never counted as a pass."""

    status: Literal["pass", "fail", "not_available", "not_run", "error"]
    case_id: str | None = None
    total: int | None = None
    passed: int | None = None
    failed: int | None = None
    errored: int | None = None
    reason: str | None = None
    duration_s: float | None = None
    failures: list[ReferenceTestFailure] = Field(default_factory=list, max_length=10)


class ModelReviewResult(Contract):
    status: Literal["accept", "reject", "uncertain", "error", "not_run"]
    reasons: list[str] = Field(default_factory=list)
    error: str | None = None


class VerificationResult(Contract):
    syntax: SyntaxCheck
    rubric: RubricCheck
    reference_tests: ReferenceTestsResult
    model_review: ModelReviewResult
    disposition: Disposition
    disposition_reasons: list[str] = Field(default_factory=list)


class RunnerInfo(Contract):
    enabled: bool
    reason: str | None = None
    isolation: dict[str, bool] = Field(default_factory=dict)


class ReferenceRunner(Protocol):
    """Executes trusted reference tests against candidate text outside the API process."""

    def info(self) -> RunnerInfo: ...

    def run(self, case: ReferenceCase, candidate_code: str) -> ReferenceTestsResult: ...


# --- Workflow and run records ---------------------------------------------------------


class WorkflowSettings(Contract):
    """Declared budgets. Total generation calls never exceed max_calls (default 5)."""

    mode: WorkflowMode = WorkflowMode.MULTI_ROLE
    refactor_use_adapter: bool = False
    max_calls: int = Field(default=5, ge=1, le=5)
    max_corrections: int = Field(default=1, ge=0, le=1)
    run_timeout_s: float = Field(default=600.0, gt=0.0, le=3600.0)
    # Limits measured on the demonstration laptop (experiments/models/): a maximal input is
    # about 910 prompt tokens and a full proposal at most about 600 completion tokens.
    generation: dict[Role, GenerationConfig] = Field(
        default_factory=lambda: {
            Role.ANALYSIS: GenerationConfig(
                max_new_tokens=384, max_input_tokens=2048, timeout_s=60.0
            ),
            Role.REFACTOR: GenerationConfig(
                max_new_tokens=1024, max_input_tokens=2048, timeout_s=120.0
            ),
            Role.REVIEW: GenerationConfig(
                max_new_tokens=768, max_input_tokens=4096, timeout_s=90.0
            ),
        }
    )


class WorkflowRequest(Contract):
    code: str
    task_type: str
    reference_case: ReferenceCase | None = None


class StageTiming(Contract):
    stage: Literal["validation", "analysis", "generation", "review", "verification"]
    attempt: int = Field(ge=0)
    started_at: datetime
    elapsed_s: float = Field(ge=0.0)
    calls: int = Field(default=0, ge=0)


class AttemptRecord(Contract):
    """One generation attempt (0 = first proposal, 1 = the single correction)."""

    attempt: int = Field(ge=0)
    raw_output: str | None = None
    parse_error: str | None = None
    parse_repaired: bool = False
    proposed_code: str | None = None
    explanation: str | None = None
    verification: VerificationResult | None = None
    review: ReviewResult | None = None
    model: ModelReference | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    elapsed_s: float | None = None


class RunError(Contract):
    code: str
    message: str
    stage: str | None = None


class WorkflowOutcome(Contract):
    """What the coordinator returns; the API adds identity and timestamps."""

    status: Literal[RunStatus.COMPLETED, RunStatus.FAILED]
    provider_mode: ProviderMode
    model: ModelReference | None = None
    analysis: AnalysisReport | None = None
    findings: list[RoleFinding] = Field(default_factory=list)
    proposed_code: str | None = None
    explanation: str | None = None
    diff: str | None = None
    changed_lines: list[int] = Field(default_factory=list)
    review: ReviewResult | None = None
    verification: VerificationResult | None = None
    attempts: list[AttemptRecord] = Field(default_factory=list)
    attempt_count: int = Field(default=0, ge=0)
    call_count: int = Field(default=0, ge=0)
    stage_timings: list[StageTiming] = Field(default_factory=list)
    stop_reason: str | None = None
    error: RunError | None = None
    warnings: list[str] = Field(default_factory=list)


StatusCallback = Callable[[RunStatus], None]


class RunRecord(Contract):
    schema_version: int = SCHEMA_VERSION
    run_id: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: RunStatus
    task_type: str
    workflow_mode: WorkflowMode
    reference_case_id: str | None = None
    original_code: str
    proposed_code: str | None = None
    provider_mode: ProviderMode
    model: ModelReference | None = None
    settings: WorkflowSettings
    attempt_count: int = 0
    call_count: int = 0
    stage_timings: list[StageTiming] = Field(default_factory=list)
    analysis: AnalysisReport | None = None
    findings: list[RoleFinding] = Field(default_factory=list)
    explanation: str | None = None
    diff: str | None = None
    changed_lines: list[int] = Field(default_factory=list)
    review: ReviewResult | None = None
    verification: VerificationResult | None = None
    attempts: list[AttemptRecord] = Field(default_factory=list)
    stop_reason: str | None = None
    error: RunError | None = None
    warnings: list[str] = Field(default_factory=list)
    human_decision: Literal["accepted", "rejected"] | None = None


# --- HTTP API -------------------------------------------------------------------------


class RunCreateRequest(Contract):
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)
    task_type: Literal["guard_clauses"] = "guard_clauses"
    workflow_mode: WorkflowMode = WorkflowMode.MULTI_ROLE
    reference_case_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_.-]{0,95}$")

    @field_validator("code")
    @classmethod
    def require_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value


class RunAccepted(Contract):
    run_id: str
    status: RunStatus
    poll_url: str


class RunSummary(Contract):
    run_id: str
    created_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    disposition: Disposition | None = None
    task_type: str
    workflow_mode: WorkflowMode
    provider_mode: ProviderMode
    reference_case_id: str | None = None
    human_decision: Literal["accepted", "rejected"] | None = None


class RunList(Contract):
    runs: list[RunSummary]
    limit: int


class DecisionRequest(Contract):
    decision: Literal["accepted", "rejected"]


class ReferenceCaseSummary(Contract):
    case_id: str
    title: str | None = None
    function_name: str
    code: str
    test_count: int


class QueueInfo(Contract):
    max_pending: int
    pending: int


class HealthResponse(Contract):
    status: Literal["ok"] = "ok"
    version: str
    mode: ProviderMode
    provider: ProviderInfo
    runner: RunnerInfo
    queue: QueueInfo
    refactor_use_adapter: bool = False


class ErrorDetail(Contract):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorResponse(Contract):
    error: ErrorDetail

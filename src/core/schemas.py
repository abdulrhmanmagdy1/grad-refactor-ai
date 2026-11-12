"""Pydantic v2 schemas for all system contracts and data records."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Providers that may be explicitly selected for a run (Phase 2 upgrade).
SUPPORTED_PROVIDERS = ("mock", "smart_ast", "ollama", "local", "local_lora", "auto")


class RunStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class CodeInput(BaseModel):
    """Bounded Python code input schema (FR01, NFR01)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        min_length=1,
        max_length=20000,
        description="Python code text up to 20,000 characters.",
    )

    @field_validator("code")
    @classmethod
    def validate_code_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value


class ASTFinding(BaseModel):
    """Structured code smell or refactoring opportunity finding (FR02)."""

    rule: str = Field(..., description="Rule identifier (e.g., long-function, deep-nesting).")
    line: int = Field(..., description="1-indexed starting line number of the finding.")
    end_line: int | None = Field(default=None, description="Ending line number if available.")
    node_type: str = Field(..., description="AST node type name (e.g., FunctionDef, If).")
    message: str = Field(..., description="Human-readable explanation of the issue.")
    rationale: str = Field(..., description="Technical rationale for the refactoring.")


class ASTGraphNode(BaseModel):
    """A single interactive node in the AST constellation (Phase 1, Phase 6)."""

    id: str = Field(..., description="Stable unique node identifier.")
    label: str = Field(..., description="Display label (symbol name or construct).")
    type: str = Field(..., description="Node kind: module, function, async_function, class, if...")
    line: int = Field(..., description="1-indexed source line of the construct.")
    complexity: int = Field(default=1, description="Cyclomatic complexity of the subtree.")
    has_smell: bool = Field(default=False, description="Whether a detector flagged this node.")
    smell_type: str | None = Field(
        default=None, description="Detector rule that flagged this node, if any."
    )


class ASTGraphEdge(BaseModel):
    """A parent-child structural edge between two AST constellation nodes."""

    source: str = Field(..., description="Parent node identifier.")
    target: str = Field(..., description="Child node identifier.")


class ASTGraph(BaseModel):
    """Serializable AST structure graph consumed by the 3D spatial frontend (Phase 1/6)."""

    nodes: list[ASTGraphNode] = Field(default_factory=list, description="Graph nodes.")
    edges: list[ASTGraphEdge] = Field(default_factory=list, description="Parent-child edges.")


class AnalysisResult(BaseModel):
    """Static AST heuristics analysis result (FR02, NFR01)."""

    syntax_valid: bool = Field(..., description="Whether input code parsed cleanly.")
    findings: list[ASTFinding] = Field(default_factory=list, description="Detected code smells.")
    error: str | None = Field(
        default=None, description="Syntax or parsing error message if invalid."
    )
    engine: str = Field(default="static-heuristics-v2", description="Analysis engine identifier.")
    metrics: dict[str, Any] = Field(default_factory=dict, description="AST structural metrics.")
    ast_graph: ASTGraph | None = Field(
        default=None, description="AST constellation graph for spatial rendering (Phase 6)."
    )


class AnalysisPlan(BaseModel):
    """Structured analysis/strategy plan produced by the Analysis Agent (Phase 3)."""

    primary_smell: str | None = Field(default=None, description="Dominant detected smell rule.")
    refactoring_strategy: str = Field(..., description="Selected refactoring strategy.")
    target_symbols: list[str] = Field(
        default_factory=list, description="Functions/classes selected for transformation."
    )
    risk_level: str = Field(default="low", description="Estimated risk: low, medium, or high.")
    step_by_step_plan: list[str] = Field(
        default_factory=list, description="Ordered deterministic execution plan."
    )


class AgentTrace(BaseModel):
    """Recorded reasoning/evidence step exchanged between agents (Phase 3)."""

    agent: str = Field(..., description="Agent role: analysis, refactoring, or review.")
    phase: str = Field(..., description="Workflow phase label (plan, generate, review...).")
    summary: str = Field(..., description="Short human-readable summary of this step.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Structured evidence (prompts, metrics, verdicts)."
    )
    duration_ms: float | None = Field(default=None, description="Step duration if measured.")


class DiffOutput(BaseModel):
    """Structured diff representation (FR05)."""

    diff: str = Field(..., description="Unified diff formatted text.")
    original_code: str = Field(..., description="Original input code.")
    refactored_code: str = Field(..., description="Candidate refactored code.")
    added_lines: int = Field(default=0, description="Count of added lines in diff.")
    removed_lines: int = Field(default=0, description="Count of removed lines in diff.")
    modified_components: list[str] = Field(
        default_factory=list, description="Names of affected functions or classes."
    )
    syntax_valid: bool = Field(..., description="Whether the refactored code has valid syntax.")


class VerificationResult(BaseModel):
    """Deterministic verification and review output (FR04, NFR06)."""

    syntax_valid: bool = Field(..., description="Whether candidate syntax is valid Python.")
    tests_available: bool = Field(
        default=False, description="Whether test suite/cases were supplied for execution."
    )
    tests_passed: bool = Field(
        default=False, description="Whether isolated tests executed and passed."
    )
    review_verdict: str = Field(
        ..., description="Review outcome: approved, rejected, or uncertain."
    )
    review_notes: str = Field(..., description="Summary notes from review agent.")
    preserved_symbols: bool = Field(
        default=True, description="Whether key symbols (functions/classes) were preserved."
    )
    critique_feedback: str | None = Field(
        default=None,
        description="Actionable critique fed back to the Refactoring Agent on retry (Phase 3).",
    )
    auto_generated_tests: bool = Field(
        default=False, description="Whether behavioral tests were auto-synthesized (Phase 4)."
    )
    metrics_before: dict[str, Any] = Field(
        default_factory=dict, description="Software metrics snapshot of the input code."
    )
    metrics_after: dict[str, Any] = Field(
        default_factory=dict, description="Software metrics snapshot of the candidate code."
    )
    metrics_delta: dict[str, Any] = Field(
        default_factory=dict, description="Signed metric deltas (after - before)."
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional verification diagnostics."
    )


class CreateRunRequest(BaseModel):
    """Request payload to initiate a refactoring run."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=20000, description="Input Python code.")
    test_code: str | None = Field(
        default=None,
        max_length=20000,
        description="Optional trusted test code to execute in isolated sandbox.",
    )
    refactoring_type: str | None = Field(
        default=None,
        description="Optional preferred refactoring type (e.g. extract-function).",
    )
    provider: str = Field(
        default="mock",
        description=f"Model provider, one of: {', '.join(SUPPORTED_PROVIDERS)}.",
    )
    max_retries: int = Field(
        default=1,
        ge=0,
        le=1,
        description="Maximum correction retries (bounded to max 1 by architectural specification).",
    )
    max_model_calls: int = Field(
        default=2,
        ge=1,
        le=4,
        description="Maximum model invocations allowed for the run (FR08).",
    )
    max_total_tokens: int = Field(
        default=4096,
        ge=1,
        le=100_000,
        description="Maximum generated tokens allowed before the run fails (FR08).",
    )
    max_duration_seconds: float = Field(
        default=120.0,
        gt=0,
        le=600,
        description="Maximum elapsed wall-clock seconds allowed for the run (FR08).",
    )

    @field_validator("code")
    @classmethod
    def validate_code_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(f"provider must be one of: {', '.join(SUPPORTED_PROVIDERS)}")
        return normalized


class RunRecord(BaseModel):
    """Full execution and audit trail for a refactoring run (FR07, FR10, ADR09)."""

    id: str = Field(..., description="Unique run identifier (UUID).")
    created_at: str = Field(..., description="ISO 8601 timestamp of run creation.")
    status: RunStatus = Field(..., description="Current status of the run.")
    input_code: str = Field(..., description="Original input code submitted.")
    refactoring_type: str | None = Field(
        default=None,
        description="Supported refactoring type selected for this run (FR03).",
    )
    output_code: str | None = Field(default=None, description="Refactored code if generated.")
    diff: str | None = Field(default=None, description="Unified diff text if available.")
    explanation: str | None = Field(
        default=None, description="Rationale and explanation of changes."
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict, description="Timing, latency, tokens, and complexity metrics."
    )
    metrics_before: dict[str, Any] = Field(
        default_factory=dict, description="Input software-metrics snapshot (Phase 1/6)."
    )
    metrics_after: dict[str, Any] = Field(
        default_factory=dict, description="Candidate software-metrics snapshot (Phase 1/6)."
    )
    metrics_delta: dict[str, Any] = Field(
        default_factory=dict, description="Signed software-metrics deltas (Phase 1/6)."
    )
    agent_traces: list[AgentTrace] = Field(
        default_factory=list, description="Analysis -> Refactoring -> Review reasoning trace."
    )
    auto_generated_tests: str | None = Field(
        default=None, description="Auto-synthesized golden equivalence test source (Phase 4)."
    )
    ast_graph_before: ASTGraph | None = Field(
        default=None, description="AST constellation of the input code (Phase 6)."
    )
    ast_graph_after: ASTGraph | None = Field(
        default=None, description="AST constellation of the accepted candidate code (Phase 6)."
    )
    errors: str | None = Field(default=None, description="Failure diagnostic or error trace.")
    user_feedback: str | None = Field(
        default=None, description="User decision: 'accepted' or 'rejected'."
    )
    feedback_comment: str | None = Field(
        default=None, description="Optional user commentary on decision."
    )
    verification: VerificationResult | None = Field(
        default=None, description="Full verification details."
    )
    findings: list[ASTFinding] = Field(
        default_factory=list, description="Static AST findings detected."
    )


class FeedbackRequest(BaseModel):
    """User feedback payload (FR06)."""

    decision: str = Field(..., description="Accepted or rejected.")
    comment: str | None = Field(default=None, description="Optional explanation of feedback.")

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        lowered = value.strip().lower()
        if lowered not in ("accepted", "rejected"):
            raise ValueError("decision must be either 'accepted' or 'rejected'")
        return lowered


class ProviderInfo(BaseModel):
    """Availability report for one selectable model provider (Phase 6)."""

    id: str = Field(..., description="Provider identifier used in CreateRunRequest.")
    label: str = Field(..., description="Human-readable provider name.")
    available: bool = Field(..., description="Whether the provider can serve a run right now.")
    engine: str = Field(..., description="Underlying engine description.")
    detail: str = Field(..., description="Availability explanation or remediation hint.")

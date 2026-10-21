"""Records of the project review mode: findings, fixes and the run record."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from refactor_ai.contracts import Disposition, ModelReference

PROJECT_SCHEMA_VERSION = 1


class Category(StrEnum):
    BUG = "bug"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    QUALITY = "quality"
    REFACTORING = "refactoring"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


class ProjectStatus(StrEnum):
    QUEUED = "queued"
    INDEXING = "indexing"
    SCANNING = "scanning"
    REVIEWING = "reviewing"
    FIXING = "fixing"
    COMPLETED = "completed"
    FAILED = "failed"


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Finding(Record):
    """One problem, from a static rule or an agent, at a place in the project."""

    id: str
    category: Category
    severity: Severity
    source: str = Field(
        description="static:ruff:<rule>, static:index:<rule>, static:task:..., agent:<role>"
    )
    file: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    symbol: str | None = Field(default=None, description="Enclosing function or module")
    title: str
    explanation: str
    evidence: str | None = None
    recommendation: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    fixable: bool = False
    also_reported_by: list[str] = Field(default_factory=list)


class FixCheck(Record):
    status: str
    detail: str | None = None


class Fix(Record):
    """A proposed change to one function that addresses its fixable findings."""

    id: str
    finding_ids: list[str]
    file: str
    symbol: str
    line_start: int
    line_end: int
    original: str
    proposed: str | None = None
    imports: list[str] = Field(default_factory=list)
    explanation: str | None = None
    diff: str | None = None
    produced_by: str
    syntax: FixCheck
    static_recheck: FixCheck
    tests: FixCheck
    review: FixCheck
    review_reasons: list[str] = Field(default_factory=list)
    disposition: Disposition
    disposition_reasons: list[str] = Field(default_factory=list)
    decision: str | None = None


class AgentCall(Record):
    role: str
    target: str
    status: str
    elapsed_s: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    error: str | None = None
    raw_output: str | None = None


class StageTime(Record):
    stage: str
    seconds: float


class ProjectRecord(Record):
    schema_version: int = PROJECT_SCHEMA_VERSION
    project_id: str
    name: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: ProjectStatus
    progress: str | None = None
    run_tests: bool = False
    summary: dict = Field(default_factory=dict)
    architecture: dict = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    fixes: list[Fix] = Field(default_factory=list)
    baseline_tests: dict | None = None
    model: ModelReference | None = None
    calls: list[AgentCall] = Field(default_factory=list)
    stage_times: list[StageTime] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    skipped_files: list[dict] = Field(default_factory=list)
    error: dict | None = None

"""Case-level evaluation record, one JSON line per (case, arm) attempt.

Every attempt is recorded, including failures, timeouts and harness exceptions, so the
denominators in the report always count every attempted case. A measurement that could
not be taken is null and null_reasons says why; nothing missing is ever written as 0.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RECORD_SCHEMA_VERSION = 1
# JSON writers may leave these raw inside strings, and str.splitlines() splits on them.
RAW_LINE_BREAKS = {"\u0085": "\\u0085", "\u2028": "\\u2028", "\u2029": "\\u2029"}


class RecordFileError(ValueError):
    """A JSON-lines file holds a line that is not one complete JSON value."""


def read_jsonl(path: Path) -> list[dict]:
    """Parse a JSON-lines file, one value per LF-terminated line.

    Lines are split on LF only: str.splitlines() would also split on U+0085, U+2028 and
    U+2029, which may appear raw inside JSON strings. A line that does not parse raises
    RecordFileError naming the file, line number and byte offset; an unterminated last
    line is reported as a probable interrupted write.
    """
    data = path.read_bytes()
    rows = []
    offset = 0
    for number, raw in enumerate(data.split(b"\n"), start=1):
        start, offset = offset, offset + len(raw) + 1
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw.decode("utf-8")))
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
            last = offset > len(data)
            note = (
                "; it is the last line and has no line ending, so an interrupted write "
                "probably cut it (resuming the run moves it aside)"
                if last
                else ""
            )
            raise RecordFileError(
                f"{path}: line {number} (byte offset {start}) is not a complete JSON "
                f"record: {exc}{note}"
            ) from exc
    return rows


def jsonl_line(record: BaseModel) -> str:
    """One record as a JSON line whose only line break is the final LF."""
    text = record.model_dump_json()
    for raw, escaped in RAW_LINE_BREAKS.items():
        text = text.replace(raw, escaped)
    return text + "\n"


FailureType = Literal[
    "none",
    "provider_timeout",
    "provider_error",
    "run_timeout",
    "unparseable_output",
    "invalid_settings",
    "reference_case_mismatch",
    "internal_error",
    "failed_other",
    "harness_exception",
]
TIMEOUT_FAILURES = ("provider_timeout", "run_timeout")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CallMeasurement(Strict):
    """One provider call as observed by the harness's metering wrapper."""

    index: int = Field(ge=0)
    role: str
    use_adapter: bool
    model: dict | None = None
    elapsed_s: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    error_code: str | None = None
    output: str = ""


class ReferenceTestSummary(Strict):
    status: str
    total: int | None = None
    passed: int | None = None
    failed: int | None = None
    errored: int | None = None
    reason: str | None = None


class Recheck(BaseModel):
    """The harness's own syntax and rubric check of the final proposal (no execution)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    syntax: Literal["pass", "fail", "no_output"]
    rubric: Literal["pass", "fail", "not_run", "no_output"]
    rubric_failed_checks: list[str] = Field(default_factory=list)
    agrees_with_workflow: bool | None = None


class EvaluationRecord(Strict):
    schema_version: int = RECORD_SCHEMA_VERSION
    evaluation_id: str
    protocol_version: str
    protocol_status: Literal["draft", "frozen"]
    arm: Literal["A", "B", "C", "D"]
    order_position: int | None = None
    case_id: str
    split: str
    source: str
    source_group: str
    dataset_sha256: str
    split_sha256: str
    code_sha: str | None
    started_at: str
    provider_mode: str | None
    model: dict | None
    models_used: list[dict] = Field(default_factory=list)
    settings: dict
    generation_seed: int
    input_sha256: str
    output_sha256: str | None
    proposed_code: str | None
    explanation: str | None
    run_status: Literal["completed", "failed"] | None
    disposition: str | None
    disposition_reasons: list[str] = Field(default_factory=list)
    stop_reason: str | None
    error: dict | None
    failure_type: FailureType
    syntax: Literal["pass", "fail", "not_run"]
    rubric: Literal["pass", "fail", "not_run"]
    rubric_failed_checks: list[str] = Field(default_factory=list)
    reference_tests: ReferenceTestSummary
    model_review: str
    recheck: Recheck
    proposal_ready: bool
    attempt_count: int | None
    reported_call_count: int | None
    calls: list[CallMeasurement] = Field(default_factory=list)
    call_count: int = Field(ge=0)
    calls_by_role: dict[str, int] = Field(default_factory=dict)
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_s: float = Field(ge=0.0)
    stage_timings: list[dict] = Field(default_factory=list)
    worker_peak_rss_mb: float | None
    gpu_memory_used_mb: float | None
    null_reasons: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    evaluator: str

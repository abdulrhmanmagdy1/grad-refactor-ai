"""Pure helpers that create and update RunRecord values.

The service, the store's startup recovery, the API and the example export all use these
functions, so a record looks the same whichever path produced it.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from refactor_ai.contracts import (
    TERMINAL_STATUSES,
    Disposition,
    ProviderMode,
    ReferenceCase,
    RunError,
    RunRecord,
    RunStatus,
    RunSummary,
    WorkflowMode,
    WorkflowOutcome,
    WorkflowSettings,
)
from refactor_ai.runs.errors import (
    PROPOSAL_MISSING,
    PROPOSAL_NOT_FINISHED,
    RunErrorCode,
)

RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# Every WorkflowOutcome field and where it goes in the RunRecord (same names).
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

INTERRUPTED_MESSAGE = (
    "The service stopped before this run finished. It was not rerun; submit the code "
    "again to retry."
)
NOT_STARTED_MESSAGE = (
    "The service stopped before this run started. It was not run; submit the code again to retry."
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_run_id() -> str:
    """32 lowercase hex characters from uuid4: URL-safe and not guessable."""
    return uuid.uuid4().hex


def is_valid_run_id(value: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(value))


def normalize_newlines(code: str) -> str:
    """CRLF and lone CR become LF, as Python's own tokenizer reads them."""
    return code.replace("\r\n", "\n").replace("\r", "\n")


def matches_reference_case(code: str, case: ReferenceCase) -> bool:
    """Equal after newline normalization; trailing whitespace at the end is ignored."""
    return normalize_newlines(code).rstrip() == normalize_newlines(case.original_code).rstrip()


def new_record(
    *,
    run_id: str,
    created_at: datetime,
    code: str,
    task_type: str,
    workflow_mode: WorkflowMode,
    provider_mode: ProviderMode,
    reference_case_id: str | None = None,
    refactor_use_adapter: bool = False,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        created_at=created_at,
        status=RunStatus.QUEUED,
        task_type=task_type,
        workflow_mode=workflow_mode,
        reference_case_id=reference_case_id,
        original_code=code,
        provider_mode=provider_mode,
        settings=WorkflowSettings(mode=workflow_mode, refactor_use_adapter=refactor_use_adapter),
    )


def apply_outcome(record: RunRecord, outcome: WorkflowOutcome, finished_at: datetime) -> RunRecord:
    """The terminal record: identity and input from the record, results from the outcome."""
    data = record.model_dump()
    for name in OUTCOME_FIELDS:
        data[name] = getattr(outcome, name)
    data["finished_at"] = finished_at
    return RunRecord.model_validate(data)


def failed_record(
    record: RunRecord, finished_at: datetime, code: str, message: str, stage: str | None
) -> RunRecord:
    """Mark a record failed with a service-level error; earlier evidence is kept."""
    return record.model_copy(
        update={
            "status": RunStatus.FAILED,
            "finished_at": finished_at,
            "error": RunError(code=code, message=message, stage=stage),
        }
    )


def interrupted_record(record: RunRecord, now: datetime, *, started: bool = True) -> RunRecord:
    """Startup recovery and shutdown: a non-terminal run becomes failed/interrupted."""
    message = INTERRUPTED_MESSAGE if started else NOT_STARTED_MESSAGE
    return failed_record(record, now, RunErrorCode.INTERRUPTED, message, record.status.value)


def disposition_of(record: RunRecord) -> Disposition | None:
    if record.verification is not None:
        return record.verification.disposition
    if record.status == RunStatus.FAILED:
        return Disposition.FAILED
    return None


def summarize(record: RunRecord) -> RunSummary:
    return RunSummary(
        run_id=record.run_id,
        created_at=record.created_at,
        finished_at=record.finished_at,
        status=record.status,
        disposition=disposition_of(record),
        task_type=record.task_type,
        workflow_mode=record.workflow_mode,
        provider_mode=record.provider_mode,
        reference_case_id=record.reference_case_id,
        human_decision=record.human_decision,
    )


def proposal_problem(record: RunRecord) -> str | None:
    """None when the proposal can be downloaded or decided on, else the reason it cannot.

    A proposal is available once the run has completed with proposed code, whatever the
    disposition: the person sees the verification results before deciding.
    """
    if record.status not in TERMINAL_STATUSES:
        return PROPOSAL_NOT_FINISHED
    if record.status != RunStatus.COMPLETED or not record.proposed_code:
        return PROPOSAL_MISSING
    return None

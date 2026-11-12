"""FastAPI route handlers for Analysis, Runs, and Feedback (FR01-FR07, FR10)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status

from agents.orchestrator import WorkflowOrchestrator
from api.dependencies import get_db, get_orchestrator
from api.reports import render_run_report
from core.ast_analyzer import analyze
from core.db import DatabaseManager
from core.schemas import (
    AnalysisResult,
    CodeInput,
    CreateRunRequest,
    FeedbackRequest,
    ProviderInfo,
    RunRecord,
    RunStatus,
)
from models.registry import provider_catalog

router = APIRouter()
VERSION = "0.1.0"

DbDep = Annotated[DatabaseManager, Depends(get_db)]
OrchDep = Annotated[WorkflowOrchestrator, Depends(get_orchestrator)]


@router.get("/health", tags=["Operations"])
def health() -> dict[str, str]:
    """Service health and capability reporting."""
    return {"status": "ok", "version": VERSION, "mode": "production"}


@router.get(
    "/api/v1/providers",
    tags=["Analysis"],
    response_model=list[ProviderInfo],
    summary="List selectable model providers with live availability",
)
def list_providers() -> list[ProviderInfo]:
    """Report provider availability for the frontend selector (Phase 6).

    Availability is probed live (Ollama daemon, HuggingFace stack) with a
    short cache so UI polling stays cheap and honest: a provider that cannot
    serve a run right now is reported ``available: false`` with remediation
    hints instead of failing later mid-run (NFR06).
    """
    return [ProviderInfo(**entry) for entry in provider_catalog()]


@router.post("/api/v1/analyze", response_model=AnalysisResult, tags=["Analysis"])
def analyze_code(request: CodeInput) -> AnalysisResult:
    """Analyze Python code using static AST heuristics without executing code (NFR01)."""
    return analyze(request.code)


@router.post(
    "/runs",
    tags=["Runs"],
    response_model=RunRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate refactoring workflow",
    responses={429: {"description": "The concurrency cap is already in use"}},
)
async def create_run(
    request: CreateRunRequest,
    background_tasks: BackgroundTasks,
    database: DbDep,
    orch: OrchDep,
    sync: bool = Query(default=False, description="Wait and execute synchronously"),
) -> RunRecord:
    """Initiate a multi-agent refactoring run (FR03, FR07)."""
    if not orch.has_capacity():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many runs in flight ({orch.active_runs}/{orch.max_concurrent_runs}). "
                "Wait for a running workflow to finish and try again."
            ),
        )
    run_id = str(uuid.uuid4())

    if sync:
        return await orch.execute_run(request, run_id=run_id)

    # Queued asynchronous run
    now_iso = datetime.now(UTC).isoformat()
    record = RunRecord(
        id=run_id,
        created_at=now_iso,
        status=RunStatus.QUEUED,
        input_code=request.code,
        refactoring_type=request.refactoring_type,
        metrics={
            "max_retries_allowed": request.max_retries,
            "limits": {
                "max_model_calls": request.max_model_calls,
                "max_total_tokens": request.max_total_tokens,
                "max_duration_seconds": request.max_duration_seconds,
                "max_retries": request.max_retries,
            },
        },
        findings=[],
    )
    database.create_run(record)
    background_tasks.add_task(orch.execute_run, request, run_id)
    return record


@router.get(
    "/runs/{run_id}",
    tags=["Runs"],
    response_model=RunRecord,
    summary="Poll run status and results",
)
def get_run(
    run_id: str,
    database: DbDep,
) -> RunRecord:
    """Retrieve run record by ID, including current state, metrics, diff, and errors (FR07)."""
    record = database.get_run(run_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with ID '{run_id}' not found.",
        )
    return record


@router.get(
    "/api/v1/stats",
    tags=["Operations"],
    summary="Aggregate statistics over the recorded runs",
)
def run_stats(database: DbDep, orch: OrchDep) -> dict:
    """Measured aggregates over the stored runs (no estimates, no invented values).

    Every number is computed from the run records in SQLite. When the history
    is larger than the sampling cap the payload reports ``truncated`` so the
    caller can tell that the aggregates cover a subset (NFR06).
    """
    stats = database.run_statistics()
    stats["runs_in_flight"] = orch.active_runs
    stats["max_concurrent_runs"] = orch.max_concurrent_runs
    return stats


@router.get(
    "/metrics",
    tags=["Operations"],
    summary="Prometheus exposition of the service metrics",
    response_class=Response,
    responses={200: {"content": {"text/plain": {}}}},
)
def prometheus_metrics(database: DbDep, orch: OrchDep) -> Response:
    """Expose the same measured aggregates in the Prometheus text format.

    The endpoint is dependency-free on purpose: the project runs with a zero
    budget, so the exposition format is rendered by hand instead of pulling in
    a client library.
    """
    stats = database.run_statistics()
    lines: list[str] = []

    lines.append("# HELP refactor_runs_total Recorded runs by status.")
    lines.append("# TYPE refactor_runs_total gauge")
    for run_status, count in sorted(stats["by_status"].items()):
        lines.append(f'refactor_runs_total{{status="{run_status}"}} {count}')

    lines.append("# HELP refactor_runs_by_verdict Recorded runs by review verdict.")
    lines.append("# TYPE refactor_runs_by_verdict gauge")
    for verdict, count in sorted(stats["by_verdict"].items()):
        lines.append(f'refactor_runs_by_verdict{{verdict="{verdict}"}} {count}')

    lines.append("# HELP refactor_runs_in_flight Runs currently executing.")
    lines.append("# TYPE refactor_runs_in_flight gauge")
    lines.append(f"refactor_runs_in_flight {orch.active_runs}")

    lines.append("# HELP refactor_run_duration_ms_mean Mean measured run duration.")
    lines.append("# TYPE refactor_run_duration_ms_mean gauge")
    lines.append(f"refactor_run_duration_ms_mean {stats['mean_duration_ms'] or 0}")

    lines.append("# HELP refactor_acceptance_rate Share of reviewed runs approved.")
    lines.append("# TYPE refactor_acceptance_rate gauge")
    acceptance = stats["acceptance_rate"]
    lines.append(f"refactor_acceptance_rate {acceptance if acceptance is not None else 0}")

    lines.append("# HELP refactor_provider_available Live availability of a provider.")
    lines.append("# TYPE refactor_provider_available gauge")
    for entry in provider_catalog():
        available = 1 if entry["available"] else 0
        lines.append(f'refactor_provider_available{{provider="{entry["id"]}"}} {available}')

    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@router.get(
    "/runs/{run_id}/report",
    tags=["Runs"],
    summary="Export a stored run as a Markdown report",
    response_class=Response,
    responses={200: {"content": {"text/markdown": {}}}},
)
def get_run_report(
    run_id: str,
    database: DbDep,
    download: bool = Query(
        default=False,
        description="Set to true to send the report as a file attachment instead of inline text.",
    ),
) -> Response:
    """Render the stored run record as a portable Markdown report (FR07 evidence).

    The report contains only measured values persisted with the run; it is
    what the academic report and release notes quote, so it must never be
    hand-edited (NFR06).
    """
    record = database.get_run(run_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with ID '{run_id}' not found.",
        )
    disposition = "attachment" if download else "inline"
    return Response(
        content=render_run_report(record, version=VERSION),
        media_type="text/markdown",
        headers={"Content-Disposition": f'{disposition}; filename="run-{run_id[:8]}.md"'},
    )


@router.get(
    "/runs",
    tags=["Runs"],
    response_model=list[RunRecord],
    summary="List past runs history",
)
def list_runs(
    response: Response,
    database: DbDep,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[RunRecord]:
    """Retrieve history of previous runs (FR10).

    ``X-Total-Count`` carries the total number of stored runs so the interface
    can page honestly ("showing 50 of 222") instead of guessing whether more
    history exists.
    """
    response.headers["X-Total-Count"] = str(database.count_runs())
    return database.list_runs(limit=limit, offset=offset)


@router.post(
    "/runs/{run_id}/decision",
    tags=["Feedback"],
    response_model=RunRecord,
    include_in_schema=False,
)
@router.post(
    "/runs/{run_id}/feedback",
    tags=["Feedback"],
    response_model=RunRecord,
    summary="Record user acceptance or rejection",
)
def record_feedback(
    run_id: str,
    feedback: FeedbackRequest,
    database: DbDep,
) -> RunRecord:
    """Record user acceptance or rejection of proposed refactoring (FR06).

    Exposed both as ``/feedback`` (canonical, FR06 name) and ``/decision``
    (alias used by the 3D spatial UI).
    """
    record = database.get_run(run_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with ID '{run_id}' not found.",
        )

    updated = database.update_feedback(
        run_id=run_id,
        decision=feedback.decision,
        comment=feedback.comment,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update feedback.",
        )

    return database.get_run(run_id)  # type: ignore[return-value]

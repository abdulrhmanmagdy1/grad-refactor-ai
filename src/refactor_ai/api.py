"""HTTP API of the refactoring service.

GET /health, POST /api/v1/analyze (static heuristics), GET /api/v1/reference-cases, the
queued run API under /api/v1/runs and the project review API under /api/v1/projects. The
API never executes submitted or generated code: it parses input with ast only, and the
workflow and the separate reference runner own everything else (a project's own tests run
only when the person asks for it, in project/testrun.py). Every error body is an
ErrorResponse.

Run the service with `uvicorn refactor_ai.api:app`; its lifespan reads the
REFACTOR_AI_* settings, starts the run worker and closes the provider on shutdown.
create_app() builds an app with injected components for tests and integration.
"""

from __future__ import annotations

import ast
import logging
import os
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, TypeVar

import anyio
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from refactor_ai import __version__
from refactor_ai.analysis import AnalysisResult, analyze
from refactor_ai.config import Settings
from refactor_ai.contracts import (
    MAX_CODE_CHARS,
    DecisionRequest,
    ErrorResponse,
    HealthResponse,
    ProviderInfo,
    ReferenceCase,
    ReferenceCaseSummary,
    ReferenceRunner,
    RunAccepted,
    RunCreateRequest,
    RunList,
    RunRecord,
)
from refactor_ai.project.models import ProjectRecord
from refactor_ai.project.runtime import pair_providers, project_model_info
from refactor_ai.project.service import ProjectBusy, ProjectService, ProjectStore, record_summary
from refactor_ai.project.workspace import IntakeError
from refactor_ai.providers.base import Provider
from refactor_ai.runs import errors
from refactor_ai.runs.components import (
    RUNNER_DISABLED_REASON,
    RUNNER_STARTUP_WAIT_S,
    CaseRegistry,
    CasesUnavailableError,
    DisabledRunner,
    ProviderWarmup,
    RunnerMonitor,
    Workflow,
    adapter_problem,
    as_registry,
    build_provider,
    build_registry,
    build_runner,
    build_workflow,
    provider_health_info,
    redact_host_paths,
)
from refactor_ai.runs.records import (
    is_valid_run_id,
    matches_reference_case,
    normalize_newlines,
    proposal_problem,
    summarize,
)
from refactor_ai.runs.service import QueueFullError, RunService, ServiceNotRunningError
from refactor_ai.runs.store import RunStore

logger = logging.getLogger(__name__)

CORS_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")
# First path segments never served from the frontend build.
RESERVED_PREFIXES = frozenset({"api", "health", "docs", "redoc", "openapi.json"})
RUN_LIST_DEFAULT = 20
RUN_LIST_MAX = 50

_Endpoint = TypeVar("_Endpoint", bound=Callable[..., Any])


class AnalysisRequest(BaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)

    @field_validator("code")
    @classmethod
    def require_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value


# --- Runtime wiring ------------------------------------------------------------------


@dataclass(frozen=True)
class _Overrides:
    settings: Settings | None
    workflow: Workflow | None
    provider: Provider | None
    runner: ReferenceRunner | None
    registry: CaseRegistry | Iterable[ReferenceCase] | None


@dataclass(frozen=True)
class Runtime:
    """Everything the endpoints use, created by the lifespan and dropped at shutdown."""

    settings: Settings
    service: RunService
    registry: CaseRegistry
    runner_monitor: RunnerMonitor
    warmup: ProviderWarmup
    frontend: StaticFiles | None
    frontend_dir: Path | None
    projects: ProjectService | None = None
    project_provider: Provider | None = None


def _is_reserved(name: str) -> bool:
    """Whether a first path segment names an API prefix (Windows ignores case and
    trailing dots and spaces in file names)."""
    return name.rstrip(". ").lower() in RESERVED_PREFIXES


class _FrontendFiles(StaticFiles):
    """The built frontend. Reserved top-level names are checked on the resolved path the
    file system opens, so no spelling of the request path ('.', '..', 'api.', 'API ',
    an NTFS stream suffix) reaches a file under them."""

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        full_path, stat_result = super().lookup_path(path)
        if stat_result is None or self.directory is None:
            return full_path, stat_result
        root = Path(os.path.realpath(self.directory))
        try:
            parts = Path(full_path).relative_to(root).parts
        except ValueError:
            return "", None
        if parts and _is_reserved(parts[0]):
            return "", None
        return full_path, stat_result


def _close_provider(provider: Provider) -> None:
    try:
        provider.close()
    except Exception:
        logger.exception("Closing the model provider failed")


def _build_runtime(overrides: _Overrides) -> Runtime:
    settings = overrides.settings if overrides.settings is not None else Settings.from_env()
    provider = overrides.provider if overrides.provider is not None else build_provider(settings)
    provider, project_provider = pair_providers(settings, provider)
    try:
        if settings.runner == "disabled":
            runner: ReferenceRunner | None = DisabledRunner(RUNNER_DISABLED_REASON)
        elif overrides.runner is not None:
            runner = overrides.runner
        else:
            runner = build_runner(settings)
        registry = (
            as_registry(overrides.registry) if overrides.registry is not None else build_registry()
        )
        workflow = overrides.workflow if overrides.workflow is not None else build_workflow()
        store = RunStore(settings.db_path, settings.retention)
    except BaseException:
        _close_provider(provider)
        raise
    # The local provider loads its model in the background at startup; runs wait for it.
    warmup = ProviderWarmup(provider)
    warm_up = settings.provider == "local" and warmup.supported
    try:
        service = RunService(
            store=store,
            workflow=workflow,
            provider=provider,
            runner=runner,
            max_pending=settings.max_pending,
            refactor_use_adapter=settings.refactor_use_adapter,
            adapter_problem=(
                (lambda: adapter_problem(provider)) if settings.refactor_use_adapter else None
            ),
            wait_ready=warmup.wait if warm_up else None,
        )
        service.start()
    except BaseException:
        store.close()
        _close_provider(provider)
        raise
    if warm_up:
        warmup.start()
    runner_monitor = RunnerMonitor(runner)
    runner_monitor.start()
    runner_monitor.wait(RUNNER_STARTUP_WAIT_S)
    if settings.refactor_use_adapter and (problem := adapter_problem(provider)) is not None:
        logger.warning(problem)
    project_store = ProjectStore(settings.projects_db_path, settings.retention)
    projects = ProjectService(
        project_store,
        settings.projects_dir,
        provider_factory=lambda: project_provider,
        tests_allowed=settings.project_tests,
    )
    projects.start()
    frontend_dir = settings.frontend_dist.resolve() if settings.frontend_dist else None
    frontend = (
        _FrontendFiles(directory=frontend_dir, html=True, check_dir=False) if frontend_dir else None
    )
    logger.info(
        "Run service started: provider=%s runner=%s max_pending=%d retention=%d",
        provider.mode.value,
        settings.runner,
        settings.max_pending,
        settings.retention,
    )
    return Runtime(
        settings,
        service,
        registry,
        runner_monitor,
        warmup,
        frontend,
        frontend_dir,
        projects,
        project_provider,
    )


def _shutdown(runtime: Runtime) -> None:
    """Stop the worker, then close the provider and the store, whatever happens."""
    service = runtime.service
    grace = runtime.settings.shutdown_grace_s
    stopped = False
    if runtime.projects is not None:
        if runtime.project_provider is not None:
            _close_provider(runtime.project_provider)  # ends a review's model call at once
        runtime.projects.stop(timeout=grace)
        runtime.projects.store.close()
    try:
        stopped = service.stop(timeout=grace)
        if not stopped:
            logger.warning("The run in progress did not finish within %.1f s", grace)
    finally:
        # Closing the provider ends a generation that is still running (the local
        # provider stops its worker process), which lets the workflow return. That run
        # is recorded as interrupted, not with the error the closed provider causes.
        if not stopped:
            service.interrupt_current()
        _close_provider(service.provider)
        try:
            if not stopped and not service.join(timeout=grace):
                logger.error("The run worker is still busy; its run is marked interrupted later")
        finally:
            service.store.close()
            # Closing the provider ends a model load in progress; both threads are daemons.
            runtime.warmup.join(timeout=grace)
            # A self-check still running ends on its own (daemon thread, bounded probes).
            runtime.runner_monitor.join(timeout=1.0)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime = await anyio.to_thread.run_sync(_build_runtime, app.state.overrides)
    app.state.runtime = runtime
    try:
        yield
    finally:
        app.state.runtime = None
        await anyio.to_thread.run_sync(_shutdown, runtime)


def get_runtime(request: Request) -> Runtime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise errors.service_unavailable()
    return runtime


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]


def _documented_errors(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse} for code in status_codes}


def _load_run(runtime: Runtime, run_id: str) -> RunRecord:
    if not is_valid_run_id(run_id):
        raise errors.run_not_found()
    record = runtime.service.store.get(run_id)
    if record is None:
        raise errors.run_not_found()
    return record


def _provider_info(provider: Provider) -> ProviderInfo:
    try:
        info = provider.info()
        if not isinstance(info, ProviderInfo):
            info = ProviderInfo.model_validate(info)
    except Exception as exc:
        logger.exception("Reading the provider information failed")
        return ProviderInfo(
            provider_mode=provider.mode,
            ready=False,
            detail=f"Provider information is unavailable ({type(exc).__name__}).",
        )
    if info.detail:
        info = info.model_copy(update={"detail": redact_host_paths(info.detail)})
    return info


# --- Endpoints -----------------------------------------------------------------------

# Routes are registered on the app itself (not through an included APIRouter), so the
# app router sees them directly; this keeps 405 Allow headers and the frontend fallback exact.
_ROUTES: list[tuple[str, Callable[..., Any], dict[str, Any]]] = []


def _route(method: str, path: str, **options: Any) -> Callable[[_Endpoint], _Endpoint]:
    def register(endpoint: _Endpoint) -> _Endpoint:
        _ROUTES.append((path, endpoint, {"methods": [method], **options}))
        return endpoint

    return register


@_route("GET", "/health", response_model=HealthResponse, responses=_documented_errors(503))
def health(runtime: RuntimeDep) -> HealthResponse:
    """Actual provider mode and identity, reference runner status, queue usage and whether
    runs use the LoRA adapter."""
    service = runtime.service
    use_adapter = runtime.settings.refactor_use_adapter
    return HealthResponse(
        version=__version__,
        mode=service.provider.mode,
        provider=provider_health_info(
            _provider_info(service.provider),
            use_adapter=use_adapter,
            warming_up=runtime.warmup.in_progress,
        ),
        runner=runtime.runner_monitor.info(),
        queue=service.queue_info(),
        refactor_use_adapter=use_adapter,
    )


@_route(
    "POST", "/api/v1/analyze", response_model=AnalysisResult, responses=_documented_errors(413, 422)
)
def analyze_code(request: AnalysisRequest) -> AnalysisResult:
    """Static heuristics only (no model, no execution)."""
    try:
        return analyze(request.code)
    except MemoryError:
        # analyze() reports the other parser failures itself; Python 3.11's parser raises
        # MemoryError for deeply chained operators, which POST /api/v1/runs also rejects.
        return AnalysisResult(syntax_valid=False, findings=[], error=errors.PARSER_LIMIT_REASON)


@_route(
    "GET",
    "/api/v1/reference-cases",
    response_model=list[ReferenceCaseSummary],
    responses=_documented_errors(500, 503),
)
def list_reference_cases(runtime: RuntimeDep) -> list[ReferenceCaseSummary]:
    """The server-owned demonstration allowlist."""
    try:
        cases = runtime.registry.list_cases()
    except CasesUnavailableError:
        raise errors.reference_cases_unavailable() from None
    return [
        ReferenceCaseSummary(
            case_id=case.case_id,
            title=case.title,
            function_name=case.function_name,
            code=case.original_code,
            test_count=len(case.tests),
        )
        for case in cases
    ]


@_route(
    "POST",
    "/api/v1/runs",
    status_code=202,
    response_model=RunAccepted,
    responses=_documented_errors(413, 422, 500, 503),
)
def create_run(body: RunCreateRequest, response: Response, runtime: RuntimeDep) -> RunAccepted:
    """Queue a refactoring run. The code is parsed, never executed."""
    code = normalize_newlines(body.code)
    try:
        ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise errors.invalid_syntax(exc) from None
    case = None
    if body.reference_case_id is not None:
        try:
            case = runtime.registry.get_case(body.reference_case_id)
        except CasesUnavailableError:
            raise errors.reference_cases_unavailable() from None
        if case is None:
            raise errors.unknown_reference_case(body.reference_case_id)
        if not matches_reference_case(code, case):
            raise errors.reference_case_mismatch(case.case_id)
    try:
        record = runtime.service.submit(
            code=code,
            task_type=body.task_type,
            workflow_mode=body.workflow_mode,
            reference_case=case,
        )
    except QueueFullError:
        raise errors.busy(runtime.service.max_pending) from None
    except ServiceNotRunningError:
        raise errors.service_unavailable() from None
    poll_url = f"/api/v1/runs/{record.run_id}"
    response.headers["Location"] = poll_url
    return RunAccepted(run_id=record.run_id, status=record.status, poll_url=poll_url)


@_route("GET", "/api/v1/runs", response_model=RunList, responses=_documented_errors(422, 503))
def list_runs(
    runtime: RuntimeDep,
    limit: Annotated[int, Query(ge=1, le=RUN_LIST_MAX)] = RUN_LIST_DEFAULT,
) -> RunList:
    """Stored runs, newest first."""
    records = runtime.service.store.list_recent(limit)
    return RunList(runs=[summarize(record) for record in records], limit=limit)


@_route(
    "GET", "/api/v1/runs/{run_id}", response_model=RunRecord, responses=_documented_errors(404, 503)
)
def get_run(run_id: str, runtime: RuntimeDep) -> RunRecord:
    return _load_run(runtime, run_id)


@_route(
    "GET",
    "/api/v1/runs/{run_id}/proposal",
    response_class=Response,
    responses={
        200: {"content": {"text/x-python": {}}, "description": "The proposed code"},
        **_documented_errors(404, 409, 503),
    },
)
def download_proposal(run_id: str, runtime: RuntimeDep) -> Response:
    """The proposed code as a .py attachment; nothing is written on the host."""
    record = _load_run(runtime, run_id)
    problem = proposal_problem(record)
    if problem is not None:
        raise errors.proposal_unavailable(problem)
    return Response(
        content=(record.proposed_code or "").encode("utf-8"),
        media_type="text/x-python; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="proposal-{record.run_id}.py"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@_route(
    "POST",
    "/api/v1/runs/{run_id}/decision",
    response_model=RunRecord,
    responses=_documented_errors(404, 409, 422, 503),
)
def record_decision(run_id: str, body: DecisionRequest, runtime: RuntimeDep) -> RunRecord:
    """Record the person's accepted or rejected decision; the latest decision wins."""
    if not is_valid_run_id(run_id):
        raise errors.run_not_found()
    problems: list[str] = []

    def decide(record: RunRecord) -> RunRecord | None:
        problem = proposal_problem(record)
        if problem is not None:
            problems.append(problem)
            return None
        return record.model_copy(update={"human_decision": body.decision})

    updated = runtime.service.store.update(run_id, decide)
    if updated is None:
        raise errors.run_not_found()
    if problems:
        raise errors.proposal_unavailable(problems[0])
    return updated


@_route(
    "DELETE",
    "/api/v1/runs/{run_id}",
    status_code=204,
    response_class=Response,
    responses=_documented_errors(404, 503),
)
def delete_run(run_id: str, runtime: RuntimeDep) -> Response:
    """Delete the stored record. A waiting run is skipped; a running run's outcome is
    discarded when it finishes."""
    if not is_valid_run_id(run_id) or not runtime.service.store.delete(run_id):
        raise errors.run_not_found()
    return Response(status_code=204)


# --- Project reviews -------------------------------------------------------------------

PROJECT_LIST_MAX = 50


def _projects(runtime: Runtime) -> ProjectService:
    if runtime.projects is None:
        raise errors.service_unavailable()
    return runtime.projects


def _load_project(runtime: Runtime, project_id: str) -> ProjectRecord:
    if not is_valid_run_id(project_id):
        raise errors.project_not_found()
    record = _projects(runtime).get(project_id)
    if record is None:
        raise errors.project_not_found()
    return record


@_route("GET", "/api/v1/projects/info", responses=_documented_errors(503))
def project_info(runtime: RuntimeDep) -> dict:
    """Whether project reviews use a model, and its identity and state."""
    info = project_model_info(runtime.project_provider)
    if info.get("detail"):
        info["detail"] = redact_host_paths(info["detail"])
    return {
        **info,
        "max_zip_bytes": errors.MAX_PROJECT_BYTES,
        "tests_allowed": runtime.settings.project_tests,
    }


@_route(
    "POST",
    "/api/v1/projects",
    status_code=202,
    responses=_documented_errors(413, 422, 503),
)
async def create_project(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    name: Annotated[str, Query(max_length=120)] = "project",
    run_tests: bool = False,
) -> dict:
    """Upload a project as a zip (the raw request body) and queue its review. The files
    are only parsed; the project's own tests run only when run_tests=true."""
    data = await request.body()
    if not data:
        raise errors.invalid_project("empty", "The request body must be a zip file.")
    projects = _projects(runtime)
    try:
        record = await anyio.to_thread.run_sync(projects.submit, data, name, run_tests)
    except IntakeError as exc:
        raise errors.invalid_project(exc.code, exc.message) from None
    except ProjectBusy:
        raise errors.busy(projects.max_pending) from None
    poll_url = f"/api/v1/projects/{record.project_id}"
    response.headers["Location"] = poll_url
    return {"project_id": record.project_id, "status": record.status.value, "poll_url": poll_url}


@_route("GET", "/api/v1/projects", responses=_documented_errors(422, 503))
def list_projects(
    runtime: RuntimeDep,
    limit: Annotated[int, Query(ge=1, le=PROJECT_LIST_MAX)] = RUN_LIST_DEFAULT,
) -> dict:
    """Project reviews, newest first (short form)."""
    return {
        "projects": [record_summary(r) for r in _projects(runtime).list(limit)],
        "limit": limit,
    }


@_route(
    "GET",
    "/api/v1/projects/{project_id}",
    response_model=ProjectRecord,
    responses=_documented_errors(404, 503),
)
def get_project(project_id: str, runtime: RuntimeDep) -> ProjectRecord:
    return _load_project(runtime, project_id)


@_route(
    "POST",
    "/api/v1/projects/{project_id}/fixes/{fix_id}/decision",
    response_model=ProjectRecord,
    responses=_documented_errors(404, 409, 422, 503),
)
def decide_fix(
    project_id: str, fix_id: str, body: DecisionRequest, runtime: RuntimeDep
) -> ProjectRecord:
    """Accept or reject one fix; only accepted fixes go into the patch and the download."""
    _load_project(runtime, project_id)
    try:
        return _projects(runtime).decide(project_id, fix_id, body.decision)
    except KeyError as exc:
        if exc.args and exc.args[0] == "fix":
            raise errors.fix_not_found() from None
        raise errors.project_not_found() from None
    except LookupError as exc:
        raise errors.fix_unavailable(str(exc)) from None


def _attachment(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@_route(
    "GET",
    "/api/v1/projects/{project_id}/patch",
    response_class=Response,
    responses={
        200: {"content": {"text/x-diff": {}}, "description": "The accepted fixes"},
        **_documented_errors(404, 409, 503),
    },
)
def download_patch(project_id: str, runtime: RuntimeDep) -> Response:
    """The accepted fixes as one unified diff."""
    record = _load_project(runtime, project_id)
    try:
        patch = _projects(runtime).patch(project_id)
    except LookupError as exc:
        raise errors.fix_unavailable(str(exc)) from None
    return _attachment(
        patch.encode("utf-8"), "text/x-diff; charset=utf-8", f"{record.project_id}.patch"
    )


@_route(
    "GET",
    "/api/v1/projects/{project_id}/download",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}, "description": "The project with fixes"},
        **_documented_errors(404, 409, 503),
    },
)
def download_project(project_id: str, runtime: RuntimeDep) -> Response:
    """The project as a zip with the accepted fixes applied."""
    _load_project(runtime, project_id)
    try:
        filename, data = _projects(runtime).download(project_id)
    except LookupError as exc:
        raise errors.fix_unavailable(str(exc)) from None
    return _attachment(data, "application/zip", filename)


@_route(
    "DELETE",
    "/api/v1/projects/{project_id}",
    status_code=204,
    response_class=Response,
    responses=_documented_errors(404, 503),
)
def delete_project(project_id: str, runtime: RuntimeDep) -> Response:
    """Delete the review and the uploaded files."""
    _load_project(runtime, project_id)
    _projects(runtime).delete(project_id)
    return Response(status_code=204)


# --- Errors and middleware -----------------------------------------------------------


def _error_response(error: errors.ApiError) -> JSONResponse:
    return JSONResponse(
        error.body().model_dump(mode="json"),
        status_code=error.status_code,
        headers=error.headers or None,
    )


def _allowed_methods(request: Request) -> str | None:
    """All methods of the routes matching the path (Starlette reports only the first)."""
    path = request.scope.get("path", "")
    methods: set[str] = set()
    for route in request.app.router.routes:
        if isinstance(route, Route) and route.methods and route.path_regex.match(path):
            methods |= route.methods
    return ", ".join(sorted(methods)) or None


async def _serve_frontend(request: Request) -> Response | None:
    """The built frontend for GET/HEAD paths no route matched; reserved prefixes and
    missing files stay JSON 404s."""
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None or runtime.frontend is None or request.method not in ("GET", "HEAD"):
        return None
    first = request.scope.get("path", "/").lstrip("/").split("/", 1)[0]
    if _is_reserved(first) or not (runtime.frontend_dir / "index.html").is_file():
        return None
    try:
        return await runtime.frontend.get_response(
            runtime.frontend.get_path(request.scope), request.scope
        )
    except (StarletteHTTPException, OSError, ValueError):
        # OSError: a name the file system cannot use (on Windows '*', '"', '<', '|' or a
        # component over 255 characters); such a file cannot exist, so this is a 404.
        return None


def _body_decode_problem(exc: StarletteHTTPException) -> str | None:
    """Why the JSON body could not be decoded, when that caused FastAPI's bare 400
    ("There was an error parsing the body"); malformed JSON is a validation_error."""
    if isinstance(exc.__cause__, UnicodeDecodeError):
        return errors.BODY_NOT_UTF8
    if isinstance(exc.__cause__, RecursionError):
        return errors.BODY_TOO_DEEP
    return None


async def _handle_api_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, errors.ApiError)
    return _error_response(exc)


async def _handle_validation_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    return _error_response(errors.validation_error(exc.errors()))


async def _handle_http_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 404:
        served = await _serve_frontend(request)
        return served if served is not None else _error_response(errors.not_found())
    if exc.status_code == 405:
        allow = _allowed_methods(request) or (exc.headers or {}).get("Allow")
        return _error_response(errors.method_not_allowed(allow))
    if exc.status_code == 413:
        return _error_response(errors.payload_too_large())
    if exc.status_code == 400 and (reason := _body_decode_problem(exc)) is not None:
        return _error_response(errors.body_not_decodable(reason))
    message = exc.detail if isinstance(exc.detail, str) and exc.detail else "HTTP error."
    error = errors.ApiError(exc.status_code, errors.ErrorCode.HTTP_ERROR, message)
    error.headers = dict(exc.headers or {})
    return _error_response(error)


async def _handle_unexpected(request: Request, exc: Exception) -> Response:
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return _error_response(errors.internal_error())


class _JsonCORSMiddleware(CORSMiddleware):
    """CORS for the Vite development server; a rejected preflight gets an ErrorResponse."""

    def preflight_response(self, request_headers: Headers) -> Response:
        response = super().preflight_response(request_headers=request_headers)
        if response.status_code != 400:
            return response
        failures = bytes(response.body).decode("utf-8").removeprefix("Disallowed CORS ")
        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in ("content-length", "content-type")
        }
        error = errors.cors_rejected(failures)
        return JSONResponse(error.body().model_dump(mode="json"), status_code=400, headers=headers)


class _BodySizeLimit:
    """Reject request bodies above max_bytes with 413 before they are parsed (a project
    upload to POST /api/v1/projects may be up to MAX_PROJECT_BYTES)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.max_bytes
        if scope.get("method") == "POST" and scope.get("path") == "/api/v1/projects":
            limit = errors.MAX_PROJECT_BYTES
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await _error_response(errors.payload_too_large(limit))(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise StarletteHTTPException(status_code=413)
            return message

        await self.app(scope, limited_receive, send)


def create_app(
    settings: Settings | None = None,
    *,
    workflow: Workflow | None = None,
    provider: Provider | None = None,
    runner: ReferenceRunner | None = None,
    registry: CaseRegistry | Iterable[ReferenceCase] | None = None,
) -> FastAPI:
    """Build the application. Components left as None are created at startup from the
    settings (REFACTOR_AI_* variables when settings is None)."""
    app = FastAPI(
        title="Multi-Agent Refactoring for Python",
        version=__version__,
        description=(
            "Local refactoring service for one supported task (guard_clauses). "
            "/health reports whether the model provider is the deterministic fake or the "
            "local model. The API parses code and never executes it."
        ),
        lifespan=_lifespan,
        redirect_slashes=False,
    )
    app.state.overrides = _Overrides(settings, workflow, provider, runner, registry)
    app.state.runtime = None
    # Added last means outermost: CORS headers also reach 413 responses.
    app.add_middleware(_BodySizeLimit, max_bytes=errors.MAX_BODY_BYTES)
    app.add_middleware(
        _JsonCORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition", "Location", "Retry-After"],
    )
    app.add_exception_handler(errors.ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected)
    for path, endpoint, options in _ROUTES:
        app.add_api_route(path, endpoint, **options)
    return app


app = create_app()

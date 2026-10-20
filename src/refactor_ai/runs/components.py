"""Build the provider, reference runner, demonstration cases and workflow for the service.

Implementations owned by other workstreams are imported lazily when the service starts:
the workflow from refactor_ai.agents.coordinator, the local model from
refactor_ai.providers.local and the reference runner from refactor_ai.verification.
When one is missing or fails to load, the service says so (in /health or in each run's
error) instead of substituting a pretend result. Tests inject their own components.
"""

from __future__ import annotations

import importlib
import logging
import re
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol

from refactor_ai.config import Settings
from refactor_ai.contracts import (
    GenerationRequest,
    GenerationResult,
    ProviderErrorCode,
    ProviderInfo,
    ProviderMode,
    ReferenceCase,
    ReferenceRunner,
    ReferenceTestsResult,
    RunError,
    RunnerInfo,
    RunStatus,
    StatusCallback,
    WorkflowOutcome,
    WorkflowRequest,
    WorkflowSettings,
)
from refactor_ai.providers.base import Provider, failed_result
from refactor_ai.providers.fake import FakeProvider
from refactor_ai.runs.errors import RunErrorCode

logger = logging.getLogger(__name__)

WORKFLOW_MODULE = "refactor_ai.agents.coordinator"
LOCAL_PROVIDER_MODULE = "refactor_ai.providers.local"
VERIFICATION_MODULE = "refactor_ai.verification"
RUNNER_FACTORY = "create_runner"
DEMO_CASES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "demo_cases.json"

RUNNER_DISABLED_REASON = (
    "Reference test execution is disabled by configuration (REFACTOR_AI_RUNNER=disabled)."
)
MAX_REASON_CHARS = 300


class Workflow(Protocol):
    """The coordinator entry point: refactor_ai.agents.coordinator.run_workflow."""

    def __call__(
        self,
        request: WorkflowRequest,
        *,
        provider: Provider,
        settings: WorkflowSettings,
        runner: ReferenceRunner | None = None,
        on_status: StatusCallback | None = None,
    ) -> WorkflowOutcome: ...


class CaseRegistry(Protocol):
    """The server-owned demonstration allowlist."""

    def list_cases(self) -> list[ReferenceCase]: ...

    def get_case(self, case_id: str) -> ReferenceCase | None: ...


class CasesUnavailableError(RuntimeError):
    """The demonstration cases exist but could not be loaded."""


# --- Host-path hygiene ---------------------------------------------------------------


def redact_host_paths(text: str) -> str:
    """Replace the user's home directory with ~ so responses do not reveal host paths."""
    home = str(Path.home())
    if len(home) > 3:
        for variant in {home, home.replace("\\", "/")}:
            text = re.sub(re.escape(variant), "~", text, flags=re.IGNORECASE)
    return text


def describe_exception(exc: BaseException) -> str:
    """Exception type and message for a reason text, without host paths, bounded."""
    message = " ".join(str(exc).split())
    text = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    text = redact_host_paths(text)
    if len(text) > MAX_REASON_CHARS:
        text = text[: MAX_REASON_CHARS - 3] + "..."
    return text


def _log_load_failure(what: str, module: str, exc: BaseException) -> None:
    """A module that is simply not written yet is a warning; anything else is an error."""
    missing = isinstance(exc, ModuleNotFoundError) and exc.name is not None
    if missing and (module == exc.name or module.startswith(f"{exc.name}.")):
        logger.warning("%s is not available: module %s is not installed", what, exc.name)
    else:
        logger.error("%s could not be loaded", what, exc_info=exc)


# --- Provider ------------------------------------------------------------------------


class UnavailableProvider:
    """Stands in for a provider that could not be loaded. It never pretends to work:
    info() reports ready=False with the reason and every call fails as unavailable."""

    def __init__(self, mode: ProviderMode, reason: str) -> None:
        self._mode = mode
        self._reason = reason

    @property
    def mode(self) -> ProviderMode:
        return self._mode

    def info(self) -> ProviderInfo:
        return ProviderInfo(provider_mode=self._mode, ready=False, detail=self._reason)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return failed_result(self._mode, ProviderErrorCode.UNAVAILABLE, self._reason)

    def close(self) -> None:
        return None


def build_provider(settings: Settings) -> Provider:
    """FakeProvider for provider=fake; LocalProvider.from_config(path) for provider=local."""
    if settings.provider == "fake":
        return FakeProvider()
    try:
        module = importlib.import_module(LOCAL_PROVIDER_MODULE)
        from_config = module.LocalProvider.from_config
    except Exception as exc:
        _log_load_failure("The local model provider", LOCAL_PROVIDER_MODULE, exc)
        return UnavailableProvider(
            ProviderMode.LOCAL_MODEL,
            f"The local model provider is not available in this build ({describe_exception(exc)}).",
        )
    try:
        return from_config(settings.local_model_config)
    except Exception as exc:
        logger.exception("The local model provider could not start")
        return UnavailableProvider(
            ProviderMode.LOCAL_MODEL,
            f"The local model provider could not start ({describe_exception(exc)}).",
        )


ADAPTER_MISSING_REASON = (
    "REFACTOR_AI_REFACTOR_USE_ADAPTER=true, but the model provider has no LoRA adapter "
    "configured. Runs fail instead of using the base model."
)
MODEL_LOADING_DETAIL = (
    "The model is loading in the background since startup; runs wait until it is ready."
)
WARMUP_THREAD_NAME = "refactor-ai-model-warmup"


def adapter_problem(provider: Provider) -> str | None:
    """Why runs cannot use the LoRA adapter, or None when the provider has one.

    The provider reports a configured adapter through ProviderInfo.adapter_id. When its
    information cannot be read, None is returned and the workflow's own adapter-state
    check (model_load_error) still prevents a silent fallback to the base model.
    """
    try:
        info = provider.info()
        adapter_id = info.adapter_id if isinstance(info, ProviderInfo) else info["adapter_id"]
    except Exception:
        logger.exception("Reading the provider information for the adapter check failed")
        return None
    return None if adapter_id else ADAPTER_MISSING_REASON


def provider_health_info(
    info: ProviderInfo, *, use_adapter: bool, warming_up: bool
) -> ProviderInfo:
    """The provider information /health shows, stating plainly what blocks runs."""
    detail = info.detail
    ready = info.ready
    if warming_up and not ready:
        detail = MODEL_LOADING_DETAIL
    if use_adapter and not info.adapter_id:
        ready = False
        detail = f"{ADAPTER_MISSING_REASON} {detail}" if detail else ADAPTER_MISSING_REASON
    if detail:
        detail = redact_host_paths(detail)
    return info.model_copy(update={"ready": ready, "detail": detail})


class ProviderWarmup:
    """Calls provider.warm_up() once in a background thread at startup.

    The local provider loads the model there instead of on the first request. The call
    holds the provider's call lock, so the run worker waits for wait() before starting
    a run; /health never waits (the provider's info() does not take that lock).
    """

    def __init__(self, provider: Provider) -> None:
        self._provider = provider
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def supported(self) -> bool:
        return callable(getattr(self._provider, "warm_up", None))

    def start(self) -> bool:
        """Start the warm-up; False (and nothing to wait for) when the provider has none."""
        if not self.supported:
            self._done.set()
            return False
        self._thread = threading.Thread(target=self._warm, name=WARMUP_THREAD_NAME, daemon=True)
        self._thread.start()
        return True

    def _warm(self) -> None:
        try:
            self._provider.warm_up()  # type: ignore[attr-defined]
            logger.info("Model warm-up finished")
        except Exception:
            logger.exception("The model warm-up failed; runs report the provider's error")
        finally:
            self._done.set()

    @property
    def in_progress(self) -> bool:
        return self._thread is not None and not self._done.is_set()

    def wait(self, timeout: float) -> bool:
        return self._done.wait(timeout)

    def join(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True


# --- Reference runner ----------------------------------------------------------------


class DisabledRunner:
    """Runner used when execution is disabled or the real runner is missing: every
    result is not_run with the reason, never a pass."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def info(self) -> RunnerInfo:
        return RunnerInfo(enabled=False, reason=self._reason)

    def run(self, case: ReferenceCase, candidate_code: str) -> ReferenceTestsResult:
        return ReferenceTestsResult(status="not_run", case_id=case.case_id, reason=self._reason)


def _runner_factory() -> Callable[[], ReferenceRunner]:
    factory = getattr(importlib.import_module(VERIFICATION_MODULE), RUNNER_FACTORY, None)
    if not callable(factory):
        raise AttributeError(f"{VERIFICATION_MODULE} defines no {RUNNER_FACTORY}()")
    return factory


def build_runner(settings: Settings) -> ReferenceRunner:
    """refactor_ai.verification.create_runner() for runner=auto; its own isolation
    self-checks decide whether it executes anything. runner=disabled reports not_run."""
    if settings.runner == "disabled":
        return DisabledRunner(RUNNER_DISABLED_REASON)
    try:
        return _runner_factory()()
    except Exception as exc:
        _log_load_failure("The reference runner", VERIFICATION_MODULE, exc)
        return DisabledRunner(
            f"The reference runner is not available in this build ({describe_exception(exc)})."
        )


RUNNER_CHECKS_RUNNING = (
    "The reference runner is still running its isolation self-checks; execution is not enabled yet."
)
RUNNER_THREAD_NAME = "refactor-ai-runner-checks"
# Startup waits this long for the first reading, so fast runners are reported exactly.
RUNNER_STARTUP_WAIT_S = 1.0


def runner_info(runner: ReferenceRunner | None) -> RunnerInfo:
    """runner.info() for /health, never raising and never showing host paths."""
    if runner is None:
        return RunnerInfo(enabled=False, reason="No reference runner is configured.")
    try:
        info = runner.info()
        if not isinstance(info, RunnerInfo):
            info = RunnerInfo.model_validate(info)
    except Exception as exc:
        logger.exception("Reading the reference runner information failed")
        return RunnerInfo(
            enabled=False,
            reason=f"Reference runner information is unavailable ({type(exc).__name__}).",
        )
    if info.reason:
        info = info.model_copy(update={"reason": redact_host_paths(info.reason)})
    return info


class RunnerMonitor:
    """Reads runner.info() once in a background thread at startup.

    The real runner runs its isolation self-checks on the first info() call (about
    10 s on the demonstration laptop) and holds a lock meanwhile, so /health would
    otherwise wait for them. Until the first reading completes, info() reports that
    execution is not enabled yet, which is true.
    """

    def __init__(self, runner: ReferenceRunner | None) -> None:
        self._runner = runner
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._runner is None:
            self._done.set()
            return
        self._thread = threading.Thread(target=self._check, name=RUNNER_THREAD_NAME, daemon=True)
        self._thread.start()

    def _check(self) -> None:
        try:
            info = runner_info(self._runner)
            if info.enabled:
                logger.info("Reference runner enabled")
            elif info.reason == RUNNER_DISABLED_REASON:
                logger.info("Reference runner disabled by configuration")
            else:
                logger.warning("Reference runner disabled: %s", info.reason)
        finally:
            self._done.set()

    @property
    def checked(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: float) -> bool:
        """Wait up to timeout for the first reading; True once it is available."""
        return self._done.wait(timeout)

    def info(self) -> RunnerInfo:
        if not self._done.is_set():
            return RunnerInfo(enabled=False, reason=RUNNER_CHECKS_RUNNING)
        return runner_info(self._runner)

    def join(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True


# --- Demonstration cases -------------------------------------------------------------


class StaticCaseRegistry:
    """An in-memory allowlist of ReferenceCase objects with unique ids."""

    def __init__(self, cases: Iterable[ReferenceCase]) -> None:
        self._cases: dict[str, ReferenceCase] = {}
        for case in cases:
            if case.case_id in self._cases:
                raise ValueError(f"Duplicate reference case id {case.case_id!r}")
            self._cases[case.case_id] = case

    def list_cases(self) -> list[ReferenceCase]:
        return list(self._cases.values())

    def get_case(self, case_id: str) -> ReferenceCase | None:
        return self._cases.get(case_id)


class UnavailableCaseRegistry:
    """The demonstration cases could not be loaded; every lookup reports why."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def list_cases(self) -> list[ReferenceCase]:
        raise CasesUnavailableError(self.reason)

    def get_case(self, case_id: str) -> ReferenceCase | None:
        raise CasesUnavailableError(self.reason)


def build_registry(path: Path = DEMO_CASES_PATH) -> CaseRegistry:
    """The demonstration allowlist from refactor_ai.verification.CaseRegistry.from_file.

    That loader owns the file rules (a missing file is an empty allowlist; an invalid
    file raises). An invalid file, or a missing verification package, makes the
    allowlist unavailable rather than silently empty.
    """
    try:
        registry_type = importlib.import_module(VERIFICATION_MODULE).CaseRegistry
    except Exception as exc:
        _log_load_failure("The demonstration case registry", VERIFICATION_MODULE, exc)
        return UnavailableCaseRegistry(
            f"The demonstration case registry is not available in this build "
            f"({describe_exception(exc)})."
        )
    try:
        registry = registry_type.from_file(path)
    except Exception as exc:
        logger.error("The demonstration cases could not be loaded: %s", describe_exception(exc))
        return UnavailableCaseRegistry(describe_exception(exc))
    if not path.is_file():
        logger.warning("No demonstration cases file at %s; the allowlist is empty", path.name)
    return registry


def as_registry(cases: CaseRegistry | Iterable[ReferenceCase]) -> CaseRegistry:
    """Accept a registry object or a plain iterable of cases (convenient for tests)."""
    if hasattr(cases, "list_cases") and hasattr(cases, "get_case"):
        return cases  # type: ignore[return-value]
    return StaticCaseRegistry(cases)  # type: ignore[arg-type]


# --- Workflow ------------------------------------------------------------------------


def unavailable_workflow(reason: str) -> Workflow:
    """A workflow stand-in that fails every run with workflow_unavailable."""

    def run_workflow(
        request: WorkflowRequest,
        *,
        provider: Provider,
        settings: WorkflowSettings,
        runner: ReferenceRunner | None = None,
        on_status: StatusCallback | None = None,
    ) -> WorkflowOutcome:
        return WorkflowOutcome(
            status=RunStatus.FAILED,
            provider_mode=provider.mode,
            stop_reason=RunErrorCode.WORKFLOW_UNAVAILABLE.value,
            error=RunError(code=RunErrorCode.WORKFLOW_UNAVAILABLE, message=reason),
        )

    return run_workflow


def build_workflow() -> Workflow:
    """refactor_ai.agents.coordinator.run_workflow, or a stand-in that reports why not."""
    try:
        module = importlib.import_module(WORKFLOW_MODULE)
        workflow = module.run_workflow
    except Exception as exc:
        _log_load_failure("The workflow coordinator", WORKFLOW_MODULE, exc)
        return unavailable_workflow(
            f"The workflow coordinator is not available in this build ({describe_exception(exc)})."
        )
    return workflow

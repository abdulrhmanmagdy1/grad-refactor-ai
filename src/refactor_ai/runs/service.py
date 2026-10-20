"""The run service: bounded admission, one worker thread, persisted state transitions.

Exactly one worker thread calls the workflow, so model inference is serialized.
Admission is bounded by max_pending, the number of unfinished runs (waiting plus the one
running). Non-terminal statuses reported through on_status are stored as they happen;
the terminal status is stored together with the outcome, so a reader that sees
completed or failed always sees the full result. A workflow exception becomes a failed
run with error code internal_error and no traceback. On start, runs a previous process
left unfinished are marked failed with error code interrupted and are never rerun; on
stop, the run in progress may finish and runs still waiting are marked the same way.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from refactor_ai.contracts import (
    TERMINAL_STATUSES,
    QueueInfo,
    ReferenceCase,
    ReferenceRunner,
    RunRecord,
    RunStatus,
    WorkflowMode,
    WorkflowOutcome,
    WorkflowRequest,
)
from refactor_ai.providers.base import Provider
from refactor_ai.runs.components import Workflow
from refactor_ai.runs.errors import RunErrorCode
from refactor_ai.runs.records import (
    apply_outcome,
    failed_record,
    interrupted_record,
    new_record,
    new_run_id,
    utc_now,
)
from refactor_ai.runs.store import RunStore

logger = logging.getLogger(__name__)

WORKER_THREAD_NAME = "refactor-ai-run-worker"
OUTCOME_NOT_STORED = (
    "The run finished but its outcome could not be stored. Details are in the server log."
)
INVALID_OUTCOME = "The workflow returned an invalid outcome. Details are in the server log."


class QueueFullError(RuntimeError):
    """max_pending unfinished runs already exist."""


class ServiceNotRunningError(RuntimeError):
    """The service is not accepting runs (not started yet, or stopping)."""


@dataclass(frozen=True)
class _Job:
    run_id: str
    reference_case: ReferenceCase | None


@dataclass
class _Progress:
    status: RunStatus


_STOP = object()


def internal_error_message(exc: BaseException) -> str:
    """Names the exception type only: messages and tracebacks stay in the server log."""
    return (
        f"The workflow stopped with an internal error ({type(exc).__name__}). "
        "Details are in the server log."
    )


class RunService:
    def __init__(
        self,
        *,
        store: RunStore,
        workflow: Workflow,
        provider: Provider,
        runner: ReferenceRunner | None,
        max_pending: int,
        refactor_use_adapter: bool = False,
        clock: Callable[[], datetime] = utc_now,
        new_id: Callable[[], str] = new_run_id,
    ) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be at least 1")
        self._store = store
        self._workflow = workflow
        self._provider = provider
        self._runner = runner
        self._max_pending = max_pending
        self._use_adapter = refactor_use_adapter
        self._clock = clock
        self._new_id = new_id
        self._queue: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._pending = 0
        self._accepting = False
        self._stopping = False
        self._thread: threading.Thread | None = None

    # --- accessors -------------------------------------------------------------------

    @property
    def store(self) -> RunStore:
        return self._store

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def runner(self) -> ReferenceRunner | None:
        return self._runner

    @property
    def max_pending(self) -> int:
        return self._max_pending

    def queue_info(self) -> QueueInfo:
        with self._lock:
            return QueueInfo(max_pending=self._max_pending, pending=self._pending)

    # --- lifecycle -------------------------------------------------------------------

    def start(self) -> list[str]:
        """Recover unfinished runs, apply retention and start the worker thread.

        Returns the ids of the runs marked interrupted.
        """
        if self._thread is not None or self._stopping:
            raise RuntimeError("A run service can be started only once")
        now = self._clock()
        recovered = self._store.recover_unfinished(
            lambda record: interrupted_record(record, now, started=record.started_at is not None)
        )
        if recovered:
            logger.warning("Marked %d unfinished run(s) as interrupted", len(recovered))
        self._store.prune()
        self._thread = threading.Thread(target=self._work, name=WORKER_THREAD_NAME, daemon=True)
        self._thread.start()
        with self._lock:
            self._accepting = True
        return recovered

    def stop(self, timeout: float | None = None) -> bool:
        """Stop accepting runs; the worker finishes the run in progress, marks waiting
        runs interrupted and exits. Returns True once the worker thread has ended."""
        with self._lock:
            self._accepting = False
            if not self._stopping:
                self._stopping = True
                self._queue.put(_STOP)
        return self.join(timeout)

    def join(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    # --- submission ------------------------------------------------------------------

    def submit(
        self,
        *,
        code: str,
        task_type: str,
        workflow_mode: WorkflowMode,
        reference_case: ReferenceCase | None = None,
    ) -> RunRecord:
        """Store a queued run and hand it to the worker.

        Raises QueueFullError when max_pending runs are unfinished and
        ServiceNotRunningError when the service is not running. The input must already
        be validated by the caller.
        """
        with self._lock:
            if not self._accepting:
                raise ServiceNotRunningError("The run service is not running")
            if self._pending >= self._max_pending:
                raise QueueFullError(f"{self._pending} unfinished runs")
            record = new_record(
                run_id=self._new_id(),
                created_at=self._clock(),
                code=code,
                task_type=task_type,
                workflow_mode=workflow_mode,
                provider_mode=self._provider.mode,
                reference_case_id=None if reference_case is None else reference_case.case_id,
                refactor_use_adapter=self._use_adapter,
            )
            self._store.insert(record)
            self._pending += 1
            self._queue.put(_Job(record.run_id, reference_case))
        return record

    # --- worker ----------------------------------------------------------------------

    def _work(self) -> None:
        while True:
            job = self._queue.get()
            if job is _STOP:
                return
            if not isinstance(job, _Job):  # nothing else is ever queued
                continue
            try:
                with self._lock:
                    stopping = self._stopping
                if stopping:
                    self._mark_not_started(job.run_id)
                else:
                    self._process(job)
            except Exception:
                logger.exception("Run %s could not be processed", job.run_id)
            finally:
                with self._lock:
                    self._pending -= 1

    def _mark_not_started(self, run_id: str) -> None:
        now = self._clock()
        self._store.update(
            run_id,
            lambda record: (
                None
                if record.status in TERMINAL_STATUSES
                else interrupted_record(record, now, started=False)
            ),
        )

    def _process(self, job: _Job) -> None:
        run_id = job.run_id
        started_at = self._clock()
        record = self._store.update(
            run_id,
            lambda current: (
                None
                if current.status in TERMINAL_STATUSES
                else current.model_copy(update={"started_at": started_at})
            ),
        )
        if record is None:
            logger.info("Run %s was deleted before it started", run_id)
            return
        if record.status in TERMINAL_STATUSES:
            return
        progress = _Progress(record.status)
        try:
            request = WorkflowRequest(
                code=record.original_code,
                task_type=record.task_type,
                reference_case=job.reference_case,
            )
            result = self._workflow(
                request,
                provider=self._provider,
                settings=record.settings,
                runner=self._runner,
                on_status=self._status_callback(run_id, progress),
            )
        except Exception as exc:
            logger.exception("The workflow raised an exception for run %s", run_id)
            self._finish_failed(run_id, internal_error_message(exc), progress.status)
            return
        try:
            outcome = (
                result
                if isinstance(result, WorkflowOutcome)
                else WorkflowOutcome.model_validate(result)
            )
        except Exception:
            logger.exception("The workflow returned an invalid outcome for run %s", run_id)
            self._finish_failed(run_id, INVALID_OUTCOME, progress.status)
            return
        try:
            stored = self._store.update(
                run_id,
                lambda current: (
                    None
                    if current.status in TERMINAL_STATUSES
                    else apply_outcome(current, outcome, self._clock())
                ),
            )
        except Exception:
            logger.exception("The outcome of run %s could not be stored", run_id)
            self._finish_failed(run_id, OUTCOME_NOT_STORED, progress.status)
            return
        if stored is None:
            logger.info("Run %s was deleted while it ran; its outcome was discarded", run_id)

    def _status_callback(self, run_id: str, progress: _Progress) -> Callable[[RunStatus], None]:
        def on_status(status: RunStatus) -> None:
            try:
                value = RunStatus(status)
            except ValueError:
                logger.warning("Run %s: ignoring unknown status %r", run_id, status)
                return
            # queued is already stored; terminal statuses are stored with the outcome.
            if value in TERMINAL_STATUSES or value == RunStatus.QUEUED:
                return
            progress.status = value
            try:
                self._store.update(
                    run_id,
                    lambda current: (
                        None
                        if current.status in TERMINAL_STATUSES or current.status == value
                        else current.model_copy(update={"status": value})
                    ),
                )
            except Exception:
                logger.exception("Run %s: status %s could not be stored", run_id, value)

        return on_status

    def _finish_failed(self, run_id: str, message: str, status: RunStatus) -> None:
        now = self._clock()
        try:
            self._store.update(
                run_id,
                lambda current: (
                    None
                    if current.status in TERMINAL_STATUSES
                    else failed_record(
                        current, now, RunErrorCode.INTERNAL_ERROR, message, status.value
                    )
                ),
            )
        except Exception:
            logger.exception("Run %s could not be marked failed", run_id)

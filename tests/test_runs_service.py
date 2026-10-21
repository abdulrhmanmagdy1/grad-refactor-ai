import itertools
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from refactor_ai.contracts import (
    TERMINAL_STATUSES,
    ReferenceCase,
    RunRecord,
    RunStatus,
    StageTiming,
    WorkflowMode,
    WorkflowOutcome,
)
from refactor_ai.providers.fake import FakeProvider
from refactor_ai.runs.components import DisabledRunner
from refactor_ai.runs.records import INTERRUPTED_MESSAGE, new_record, new_run_id
from refactor_ai.runs.service import (
    INVALID_OUTCOME,
    WORKER_THREAD_NAME,
    QueueFullError,
    RunService,
    ServiceNotRunningError,
)
from refactor_ai.runs.store import RunStore
from refactor_ai.runs.testing import ScriptedWorkflow

CODE = (
    "def f(x):\n    if x is not None:\n        if x > 0:\n            return 1\n"
    "        else:\n            return 2\n    else:\n        return 0\n"
)


SERVICE_THREADS = ("refactor-ai-",)  # the run worker and the runner self-check thread


@pytest.fixture(autouse=True)
def no_leaked_workers():
    yield
    deadline = time.monotonic() + 5
    for thread in threading.enumerate():
        if thread.name.startswith(SERVICE_THREADS):
            thread.join(max(0.0, deadline - time.monotonic()))
    alive = [t for t in threading.enumerate() if t.name.startswith(SERVICE_THREADS)]
    assert alive == [], "a service thread outlived its test"


@pytest.fixture
def store(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3", retention=200)
    yield store
    store.close()


def make_service(store, workflow, *, max_pending=4, **kwargs) -> RunService:
    return RunService(
        store=store,
        workflow=workflow,
        provider=FakeProvider(),
        runner=DisabledRunner("disabled for tests"),
        max_pending=max_pending,
        **kwargs,
    )


def submit(service, code=CODE, mode=WorkflowMode.MULTI_ROLE, case=None) -> RunRecord:
    return service.submit(
        code=code, task_type="guard_clauses", workflow_mode=mode, reference_case=case
    )


def wait_terminal(store, run_id, timeout=10.0) -> RunRecord:
    deadline = time.monotonic() + timeout
    while True:
        record = store.get(run_id)
        if record is not None and record.status in TERMINAL_STATUSES:
            return record
        if time.monotonic() > deadline:
            raise AssertionError(f"run {run_id} did not finish: {record}")
        time.sleep(0.01)


def wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached")
        time.sleep(0.01)


@pytest.fixture
def running(store):
    """Start services and always stop them, even when a test fails."""
    started: list[RunService] = []

    def start(workflow, **kwargs) -> RunService:
        service = make_service(store, workflow, **kwargs)
        service.start()
        started.append(service)
        return service

    yield start
    for service in started:
        service.stop(timeout=5)


def test_run_completes_with_outcome_and_timestamps(store, running):
    timing = StageTiming(
        stage="generation", attempt=0, started_at=datetime.now(UTC), elapsed_s=0.5, calls=1
    )
    workflow = ScriptedWorkflow(
        outcome=lambda request, provider, settings: WorkflowOutcome(
            status=RunStatus.COMPLETED,
            provider_mode=provider.mode,
            proposed_code="def f(x):\n    return x\n",
            explanation="explained",
            stage_timings=[timing],
            call_count=3,
            attempt_count=1,
            stop_reason="completed",
            warnings=["w"],
        )
    )
    service = running(workflow)
    queued = submit(service)
    assert queued.status == RunStatus.QUEUED and queued.started_at is None
    done = wait_terminal(store, queued.run_id)
    assert done.status == RunStatus.COMPLETED
    assert done.proposed_code == "def f(x):\n    return x\n"
    assert done.stage_timings == [timing]
    assert (done.call_count, done.attempt_count, done.stop_reason) == (3, 1, "completed")
    assert done.warnings == ["w"]
    assert done.created_at <= done.started_at <= done.finished_at
    assert done.original_code == CODE
    assert done.provider_mode == "fake"
    assert workflow.calls[0].code == CODE
    assert workflow.calls[0].task_type == "guard_clauses"


def test_non_terminal_statuses_are_persisted_as_they_happen(store, running):
    observed = []
    service_box = {}

    def on_step(status):
        (record,) = service_box["service"].store.list_recent(1)
        observed.append(record.status)

    statuses = [
        RunStatus.QUEUED,
        RunStatus.ANALYZING,
        RunStatus.GENERATING,
        RunStatus.VERIFYING,
        RunStatus.GENERATING,  # the single correction
        RunStatus.VERIFYING,
        RunStatus.COMPLETED,
    ]
    workflow = ScriptedWorkflow(statuses=statuses, on_step=on_step)
    service = running(workflow)
    service_box["service"] = service
    run = submit(service)
    done = wait_terminal(store, run.run_id)
    # Terminal statuses are stored with the outcome, never before it.
    assert observed == [
        RunStatus.QUEUED,
        RunStatus.ANALYZING,
        RunStatus.GENERATING,
        RunStatus.VERIFYING,
        RunStatus.GENERATING,
        RunStatus.VERIFYING,
        RunStatus.VERIFYING,
    ]
    assert done.status == RunStatus.COMPLETED


def test_status_strings_and_unknown_values_are_handled(store, running):
    observed = []
    service_box = {}

    def on_step(status):
        observed.append(service_box["service"].store.list_recent(1)[0].status)

    workflow = ScriptedWorkflow(statuses=["generating", "bogus", "verifying"], on_step=on_step)
    service = running(workflow)
    service_box["service"] = service
    run = submit(service)
    assert wait_terminal(store, run.run_id).status == RunStatus.COMPLETED
    assert observed == [RunStatus.GENERATING, RunStatus.GENERATING, RunStatus.VERIFYING]


def test_workflow_exception_becomes_failed_without_details(store, running, caplog):
    secret = "C:\\Users\\someone\\secret-token-123"
    workflow = ScriptedWorkflow(
        statuses=[RunStatus.ANALYZING, RunStatus.GENERATING], error=RuntimeError(secret)
    )
    service = running(workflow)
    run = submit(service)
    failed = wait_terminal(store, run.run_id)
    assert failed.status == RunStatus.FAILED
    assert failed.error.code == "internal_error"
    assert failed.error.stage == "generating"
    assert "RuntimeError" in failed.error.message
    dumped = failed.model_dump_json()
    assert secret.replace("\\", "\\\\") not in dumped and "secret-token" not in dumped
    assert "Traceback" not in dumped
    assert failed.finished_at is not None
    assert "secret-token-123" in caplog.text  # the details stay in the server log


@pytest.mark.parametrize("result", [None, {"status": "completed"}, "text", 42])
def test_invalid_outcome_becomes_failed(store, running, result):
    workflow = ScriptedWorkflow(statuses=[], outcome=lambda *args: result)
    service = running(workflow)
    run = submit(service)
    failed = wait_terminal(store, run.run_id)
    assert failed.status == RunStatus.FAILED
    assert failed.error.code == "internal_error"
    assert failed.error.message == INVALID_OUTCOME


def test_outcome_given_as_a_mapping_is_validated(store, running):
    workflow = ScriptedWorkflow(
        statuses=[],
        outcome=lambda request, provider, settings: {
            "status": "completed",
            "provider_mode": "fake",
            "proposed_code": "def f():\n    return 1\n",
        },
    )
    service = running(workflow)
    run = submit(service)
    done = wait_terminal(store, run.run_id)
    assert done.status == RunStatus.COMPLETED
    assert done.proposed_code == "def f():\n    return 1\n"


def test_failed_outcome_keeps_the_workflow_error(store, running):
    workflow = ScriptedWorkflow(
        statuses=[RunStatus.GENERATING],
        outcome=lambda request, provider, settings: WorkflowOutcome.model_validate(
            {
                "status": "failed",
                "provider_mode": "fake",
                "error": {"code": "timeout", "message": "Generation exceeded 1.0 s"},
                "call_count": 1,
            }
        ),
    )
    service = running(workflow)
    run = submit(service)
    failed = wait_terminal(store, run.run_id)
    assert failed.status == RunStatus.FAILED
    assert failed.error.code == "timeout"
    assert failed.call_count == 1


def test_one_worker_serializes_workflow_calls(store, running):
    workflow = ScriptedWorkflow(delay_s=0.03)
    service = running(workflow, max_pending=6)
    threads_seen = []
    original = workflow.__call__

    def record_thread(*args, **kwargs):
        threads_seen.append(threading.current_thread().name)
        return original(*args, **kwargs)

    service._workflow = record_thread
    runs = [submit(service) for _ in range(6)]
    for run in runs:
        assert wait_terminal(store, run.run_id).status == RunStatus.COMPLETED
    assert workflow.max_active == 1
    assert len(workflow.calls) == 6
    assert set(threads_seen) == {WORKER_THREAD_NAME}
    # First in, first out.
    finished = [store.get(run.run_id).finished_at for run in runs]
    assert finished == sorted(finished)


def test_queue_is_bounded_and_frees_slots(store, running):
    gate = threading.Event()
    workflow = ScriptedWorkflow(gate=gate)
    service = running(workflow, max_pending=2)
    first, second = submit(service), submit(service)
    assert service.queue_info().pending == 2
    with pytest.raises(QueueFullError):
        submit(service)
    assert store.count() == 2  # the rejected run was not stored
    gate.set()
    for run in (first, second):
        assert wait_terminal(store, run.run_id).status == RunStatus.COMPLETED
    wait_until(lambda: service.queue_info().pending == 0)
    third = submit(service)
    assert wait_terminal(store, third.run_id).status == RunStatus.COMPLETED


def test_concurrent_submissions_never_exceed_the_bound(store, running):
    gate = threading.Event()
    service = running(ScriptedWorkflow(gate=gate), max_pending=3)
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(10)

    def attempt():
        barrier.wait()
        try:
            submit(service)
            outcome = "accepted"
        except QueueFullError:
            outcome = "busy"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(results) == ["accepted"] * 3 + ["busy"] * 7
    assert service.queue_info().pending == 3
    gate.set()
    wait_until(lambda: service.queue_info().pending == 0)


def test_settings_runner_and_reference_case_reach_the_workflow(store, running):
    workflow = ScriptedWorkflow()
    service = running(workflow, refactor_use_adapter=True)
    case = ReferenceCase(
        case_id="demo", task_type="guard_clauses", function_name="f", original_code=CODE
    )
    run = submit(service, mode=WorkflowMode.SINGLE_ROLE, case=case)
    done = wait_terminal(store, run.run_id)
    assert workflow.calls[0].reference_case == case
    assert workflow.settings_seen[0].mode == WorkflowMode.SINGLE_ROLE
    assert workflow.settings_seen[0].refactor_use_adapter is True
    assert done.settings == workflow.settings_seen[0]
    assert done.reference_case_id == "demo"
    assert isinstance(workflow.runners_seen[0], DisabledRunner)


def test_deterministic_clock_and_ids(store, running):
    times = (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=i) for i in itertools.count())
    ids = iter(["a" * 32, "b" * 32])
    service = running(ScriptedWorkflow(), clock=lambda: next(times), new_id=lambda: next(ids))
    run = submit(service)
    assert run.run_id == "a" * 32
    done = wait_terminal(store, run.run_id)
    # start() reads the clock once (recovery time), so the run gets the second tick.
    assert done.created_at == datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)
    assert done.started_at > done.created_at and done.finished_at > done.started_at


def test_submit_requires_a_running_service(store):
    service = make_service(store, ScriptedWorkflow())
    with pytest.raises(ServiceNotRunningError):
        submit(service)
    service.start()
    assert service.stop(timeout=5) is True
    with pytest.raises(ServiceNotRunningError):
        submit(service)
    assert service.stop(timeout=5) is True  # idempotent


def test_start_twice_is_an_error(store, running):
    service = running(ScriptedWorkflow())
    with pytest.raises(RuntimeError):
        service.start()


def test_a_stopped_service_cannot_be_restarted(store):
    service = make_service(store, ScriptedWorkflow())
    assert service.stop(timeout=1) is True
    with pytest.raises(RuntimeError):
        service.start()
    with pytest.raises(ServiceNotRunningError):
        submit(service)


def test_stop_finishes_the_current_run_and_interrupts_waiting_ones(store):
    gate = threading.Event()
    workflow = ScriptedWorkflow(gate=gate)
    service = make_service(store, workflow)
    service.start()
    try:
        first, second, third = submit(service), submit(service), submit(service)
        assert workflow.entered.wait(5)
        assert service.stop(timeout=0.1) is False  # the current run is still blocked
        gate.set()
        assert service.join(timeout=5) is True
    finally:
        gate.set()
        service.stop(timeout=5)
    assert store.get(first.run_id).status == RunStatus.COMPLETED
    for run in (second, third):
        record = store.get(run.run_id)
        assert record.status == RunStatus.FAILED
        assert record.error.code == "interrupted"
        assert record.error.stage == "queued"
        assert record.started_at is None
    assert len(workflow.calls) == 1
    assert service.queue_info().pending == 0


PROVIDER_CLOSED = WorkflowOutcome.model_validate(
    {
        "status": "failed",
        "provider_mode": "local_model",
        "error": {
            "code": "generation_error",
            "message": "The model worker exited unexpectedly (exit code 1).",
            "stage": "analysis",
        },
        "call_count": 1,
        "stop_reason": "provider_error",
    }
)


@pytest.mark.parametrize(
    "ending",
    [{"outcome": PROVIDER_CLOSED}, {"error": RuntimeError("The provider is closed.")}],
    ids=["provider-error-outcome", "exception"],
)
def test_a_run_cut_off_by_shutdown_is_interrupted(store, ending):
    """Shutdown closes the provider under a run that outlived the grace period; what the
    workflow then reports is the stop, not a model failure."""
    gate = threading.Event()
    workflow = ScriptedWorkflow(statuses=[RunStatus.ANALYZING], gate=gate, **ending)
    service = make_service(store, workflow)
    service.start()
    try:
        cut, waiting = submit(service), submit(service)
        assert workflow.entered.wait(5)
        assert service.stop(timeout=0.1) is False
        service.interrupt_current()
        gate.set()  # closing the provider ends the call
        assert service.join(timeout=5) is True
    finally:
        gate.set()
        service.stop(timeout=5)
    record = store.get(cut.run_id)
    assert record.status == RunStatus.FAILED
    assert record.error.model_dump() == {
        "code": "interrupted",
        "message": INTERRUPTED_MESSAGE,
        "stage": "analyzing",
    }
    assert record.started_at is not None and record.finished_at is not None
    assert store.get(waiting.run_id).error.code == "interrupted"
    assert len(workflow.calls) == 1


def test_a_run_finishing_within_the_grace_period_keeps_its_outcome(store):
    gate = threading.Event()
    workflow = ScriptedWorkflow(statuses=[RunStatus.ANALYZING], gate=gate, outcome=PROVIDER_CLOSED)
    service = make_service(store, workflow)
    service.start()
    try:
        run = submit(service)
        assert workflow.entered.wait(5)
        gate.set()
        assert service.stop(timeout=5) is True
    finally:
        gate.set()
        service.stop(timeout=5)
    assert store.get(run.run_id).error.code == "generation_error"


def test_start_marks_unfinished_runs_interrupted_and_never_reruns_them(store):
    created = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    queued = new_record(
        run_id=new_run_id(),
        created_at=created,
        code=CODE,
        task_type="guard_clauses",
        workflow_mode=WorkflowMode.MULTI_ROLE,
        provider_mode="fake",
    )
    timing = StageTiming(stage="analysis", attempt=0, started_at=created, elapsed_s=1.0, calls=1)
    running_record = queued.model_copy(
        update={
            "run_id": new_run_id(),
            "status": RunStatus.GENERATING,
            "started_at": created,
            "stage_timings": [timing],
        }
    )
    store.insert(queued)
    store.insert(running_record)
    workflow = ScriptedWorkflow()
    service = make_service(store, workflow)
    try:
        recovered = service.start()
        assert set(recovered) == {queued.run_id, running_record.run_id}
        time.sleep(0.1)
        assert workflow.calls == []
    finally:
        service.stop(timeout=5)
    interrupted = store.get(running_record.run_id)
    assert interrupted.status == RunStatus.FAILED
    assert interrupted.error.code == "interrupted"
    assert interrupted.error.stage == "generating"
    assert interrupted.stage_timings == [timing]  # evidence retained
    assert store.get(queued.run_id).error.code == "interrupted"


def test_run_deleted_before_it_starts_is_skipped(store, running):
    gate = threading.Event()
    workflow = ScriptedWorkflow(gate=gate)
    service = running(workflow)
    first = submit(service)
    assert workflow.entered.wait(5)
    second = submit(service)
    assert store.delete(second.run_id)
    gate.set()
    assert wait_terminal(store, first.run_id).status == RunStatus.COMPLETED
    wait_until(lambda: service.queue_info().pending == 0)
    assert len(workflow.calls) == 1
    assert store.get(second.run_id) is None


def test_run_deleted_while_running_discards_the_outcome(store, running):
    gate = threading.Event()
    workflow = ScriptedWorkflow(gate=gate)
    service = running(workflow)
    run = submit(service)
    assert workflow.entered.wait(5)
    assert store.delete(run.run_id)
    gate.set()
    wait_until(lambda: service.queue_info().pending == 0)
    assert store.get(run.run_id) is None
    assert store.count() == 0


def test_worker_survives_a_failing_store_write(store, running, monkeypatch):
    workflow = ScriptedWorkflow(statuses=[RunStatus.GENERATING])
    service = running(workflow)
    original_update = store.update
    calls = {"n": 0}

    def flaky_update(run_id, change):
        calls["n"] += 1
        if calls["n"] == 2:  # the status write fails; the run must still finish
            raise OSError("disk hiccup")
        return original_update(run_id, change)

    monkeypatch.setattr(store, "update", flaky_update)
    run = submit(service)
    assert wait_terminal(store, run.run_id).status == RunStatus.COMPLETED
    second = submit(service)
    assert wait_terminal(store, second.run_id).status == RunStatus.COMPLETED


# --- LoRA adapter requests and provider warm-up --------------------------------------


def test_adapter_request_without_an_adapter_fails_before_any_model_call(store, running):
    workflow = ScriptedWorkflow()
    reason = "no adapter configured"
    service = running(workflow, refactor_use_adapter=True, adapter_problem=lambda: reason)
    run = submit(service)
    failed = wait_terminal(store, run.run_id)
    assert failed.status == RunStatus.FAILED
    assert failed.error.code == "adapter_unavailable"
    assert failed.error.message == reason
    assert failed.error.stage is None
    assert (failed.call_count, failed.attempts, failed.proposed_code) == (0, [], None)
    assert failed.settings.refactor_use_adapter is True
    assert workflow.calls == []


def test_adapter_request_with_an_adapter_reaches_the_workflow(store, running):
    workflow = ScriptedWorkflow()
    checks = []

    def problem():
        checks.append(1)
        return None

    service = running(workflow, refactor_use_adapter=True, adapter_problem=problem)
    run = submit(service)
    assert wait_terminal(store, run.run_id).status == RunStatus.COMPLETED
    assert workflow.settings_seen[0].refactor_use_adapter is True
    assert checks == [1]


def test_adapter_check_is_skipped_when_the_adapter_is_not_requested(store, running):
    workflow = ScriptedWorkflow()
    service = running(workflow, adapter_problem=lambda: "must not be consulted")
    run = submit(service)
    assert wait_terminal(store, run.run_id).status == RunStatus.COMPLETED
    assert workflow.settings_seen[0].refactor_use_adapter is False


def test_runs_wait_for_the_provider_warm_up(store, running):
    ready = threading.Event()
    workflow = ScriptedWorkflow()
    service = running(workflow, wait_ready=ready.wait)
    try:
        run = submit(service)
        time.sleep(0.3)
        waiting = store.get(run.run_id)
        assert (waiting.status, waiting.started_at) == (RunStatus.QUEUED, None)
        assert workflow.calls == []
        assert service.queue_info().pending == 1
        ready.set()
        assert wait_terminal(store, run.run_id).status == RunStatus.COMPLETED
    finally:
        ready.set()


def test_stopping_ends_the_warm_up_wait(store):
    ready = threading.Event()
    workflow = ScriptedWorkflow()
    service = make_service(store, workflow, wait_ready=ready.wait)
    service.start()
    run = submit(service)
    started = time.monotonic()
    assert service.stop(timeout=5) is True
    assert time.monotonic() - started < 2.0
    stopped = store.get(run.run_id)
    assert stopped.status == RunStatus.FAILED
    assert stopped.error.code == "interrupted" and stopped.error.stage == "queued"
    assert workflow.calls == []


def test_warm_up_wait_is_bounded(store, running):
    workflow = ScriptedWorkflow()
    service = running(workflow, wait_ready=lambda timeout: False, ready_wait_limit_s=0.2)
    run = submit(service)
    assert wait_terminal(store, run.run_id).status == RunStatus.COMPLETED
    assert len(workflow.calls) == 1

"""Trusted reference runner: executes server-owned tests against a candidate function in a
separate, limited process, never in the calling (API) process.

Layers, each verified by info() before execution is enabled:

1. Static admission (policy.py): the candidate must be one function inside the task
   constraints, or it is not executed (not_run).
2. Process isolation: the base interpreter in isolated mode (-I -S -B), an empty
   environment (SYSTEMROOT only on Windows), a new temporary working directory that is
   removed afterwards, the payload over stdin only (no caller-chosen paths), bounded
   output and a wall-clock timeout.
3. Operating-system limits. Windows: a Job Object (committed memory, user CPU time, one
   active process, UI restrictions, kill on close) assigned while the process is still
   suspended. Linux: setrlimit for address space, CPU time, new processes (none), file
   size (zero) and core dumps, applied by the child before candidate code runs, and a
   new session so the whole process group can be killed.
4. An audit hook in the child (runner_child.py) refusing network access, process
   creation, native code, the Windows API and registry, every file write, reads outside
   the interpreter's library directories, environment changes and frame introspection.

This is not a sandbox for arbitrary untrusted code. The API offers only demonstration
cases from the server-owned allowlist; see docs/development/runner-safety.md.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from refactor_ai.contracts import (
    ReferenceCase,
    ReferenceTest,
    ReferenceTestFailure,
    ReferenceTestsResult,
    RunnerInfo,
)
from refactor_ai.tasks import guard_clauses
from refactor_ai.verification import policy, runner_child

logger = logging.getLogger(__name__)

CHILD_SCRIPT = Path(runner_child.__file__).resolve()
SUPPORTED_PLATFORMS = ("win32", "linux")
MAX_FAILURES = 10
MAX_DETAIL_CHARS = 500
CANDIDATE_FAILURES = frozenset(
    {"wrong_value", "wrong_exception", "unexpected_exception", "missing_exception"}
)
ERROR_KINDS = frozenset({"runner_error"})
DISABLED_BY_CONFIGURATION = "Reference test execution is disabled by configuration."
# The only variables the test process may see. Windows needs SYSTEMROOT, which the runner
# passes. On Linux the runner passes nothing, but the interpreter itself sets LC_CTYPE when
# it coerces the C locale to C.UTF-8 (PEP 538); -I cannot switch that off.
ALLOWED_CHILD_ENVIRONMENT = (
    frozenset({"SYSTEMROOT"}) if sys.platform == "win32" else frozenset({"LC_CTYPE"})
)


@dataclass(frozen=True)
class RunnerLimits:
    """Resource limits for one test process."""

    wall_timeout_s: float = 10.0
    cpu_time_s: float = 5.0
    memory_mb: int = 256
    max_output_bytes: int = 256 * 1024
    max_stderr_bytes: int = 16 * 1024
    max_tests: int = 200
    max_candidate_chars: int = 20_000
    max_payload_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 0 < self.wall_timeout_s <= 600:
            raise ValueError("wall_timeout_s must be in (0, 600]")
        if not 0 < self.cpu_time_s <= 600:
            raise ValueError("cpu_time_s must be in (0, 600]")
        if not 64 <= self.memory_mb <= 4096:
            raise ValueError("memory_mb must be between 64 and 4096")
        for name in (
            "max_output_bytes",
            "max_stderr_bytes",
            "max_tests",
            "max_candidate_chars",
            "max_payload_bytes",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")


@dataclass
class Execution:
    """What happened to one test process (diagnostics, never shown to users verbatim)."""

    outcome: str  # completed, timeout, cpu_limit, start_failed, output_overflow
    raw_stdout: bytes = b""
    events: list[dict] = field(default_factory=list)
    exit_code: int | None = None
    elapsed_s: float = 0.0
    stderr: str = ""
    pid: int | None = None
    isolation_applied: bool = False
    cleanup_ok: bool = False
    workdir: str | None = None
    workdir_removed: bool = False
    peak_memory_bytes: int | None = None
    detail: str | None = None

    def first(self, kind: str) -> dict | None:
        return next((event for event in self.events if event.get("t") == kind), None)

    def tests(self) -> list[dict]:
        return [event for event in self.events if event.get("t") == "test"]


def _bounded(text: str, limit: int = MAX_DETAIL_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def base_interpreter() -> str:
    """The real interpreter behind a virtual environment.

    On Windows a venv's python.exe is a launcher that starts the base interpreter as a
    second process, which a one-process job would refuse. The test process needs only the
    standard library, so the base interpreter in isolated mode is sufficient.
    """
    return getattr(sys, "_base_executable", None) or sys.executable


class _BoundedIO:
    """Writes the payload and drains stdout/stderr in threads, keeping at most a cap."""

    def __init__(self, process: subprocess.Popen, payload: bytes, out_cap: int, err_cap: int):
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.overflow = False
        self._threads = [
            threading.Thread(target=self._write, args=(process.stdin, payload), daemon=True),
            threading.Thread(
                target=self._read, args=(process.stdout, self.stdout, out_cap, True), daemon=True
            ),
            threading.Thread(
                target=self._read, args=(process.stderr, self.stderr, err_cap, False), daemon=True
            ),
        ]

    def start(self) -> None:
        for thread in self._threads:
            thread.start()

    @staticmethod
    def _write(stream, payload: bytes) -> None:
        try:
            stream.write(payload)
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    def _read(self, stream, sink: bytearray, cap: int, is_stdout: bool) -> None:
        try:
            while True:
                chunk = stream.read1(65536)
                if not chunk:
                    break
                room = cap - len(sink)
                if room > 0:
                    sink.extend(chunk[:room])
                if len(chunk) > room and is_stdout:
                    self.overflow = True
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    def join(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        for thread in self._threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in self._threads)


def _remove_tree(path: str) -> bool:
    for _ in range(20):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return True
        time.sleep(0.05)
    return not os.path.exists(path)


def _parse_events(data: bytes, nonce: str) -> list[dict]:
    """Result lines carry the run's random nonce; anything else on the channel is ignored."""
    prefix = nonce + " "
    events: list[dict] = []
    for raw in data.split(b"\n"):
        line = raw.decode("utf-8", errors="replace").rstrip("\r")
        if not line.startswith(prefix):
            continue
        try:
            event = json.loads(line[len(prefix) :])
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _reap(process: subprocess.Popen, timeout_s: float = 10.0) -> bool:
    """Wait for a terminated process without ever blocking the caller indefinitely."""
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        logger.error("Test process %s did not exit after termination", process.pid)
        return False
    return True


UNPRIVILEGED_ID = 65534  # "nobody" on Linux


def privilege_drop() -> dict:
    """Popen arguments that start the test process as an unprivileged user under root.

    RLIMIT_NPROC does not bind the root user, so a service running as root (for example
    in a container or a Kaggle session) would otherwise leave process creation unlimited
    and the process-limit self-check fails. Elsewhere the child keeps the caller's user.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0:
        return {}
    return {"user": UNPRIVILEGED_ID, "group": UNPRIVILEGED_ID, "extra_groups": []}


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _group_empty(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return True  # the id now belongs to another user's process group, not ours
    return False


class SubprocessReferenceRunner:
    """ReferenceRunner executing each case in a fresh, limited child process."""

    accepts_timeout = True

    def __init__(
        self,
        limits: RunnerLimits | None = None,
        *,
        enabled: bool = True,
        disabled_reason: str | None = None,
        work_root: str | os.PathLike[str] | None = None,
        interpreter: str | None = None,
    ) -> None:
        self.limits = limits or RunnerLimits()
        self._configured = enabled
        self._disabled_reason = disabled_reason or DISABLED_BY_CONFIGURATION
        self._work_root = None if work_root is None else os.fspath(work_root)
        self.interpreter = interpreter or base_interpreter()
        self._info: RunnerInfo | None = None
        self._lock = threading.Lock()
        self.last_execution: Execution | None = None

    # --- ReferenceRunner interface ----------------------------------------------------

    def info(self) -> RunnerInfo:
        """Isolation self-check results; computed on first use and cached."""
        with self._lock:
            if self._info is None:
                self._info = self._compute_info()
            return self._info

    def refresh(self) -> RunnerInfo:
        """Run the isolation self-checks again."""
        with self._lock:
            self._info = self._compute_info()
            return self._info

    def run(
        self, case: ReferenceCase, candidate_code: str, *, timeout_s: float | None = None
    ) -> ReferenceTestsResult:
        """Run the case's trusted tests against the candidate in a separate process.

        timeout_s, when given, lowers the wall-clock limit (the workflow passes the time
        left in the run). When that lowered limit ends the process, the run's budget ran
        out, not the candidate's: the result is not_run unless the tests that finished
        already failed or errored. Only status "pass" means every test ran and passed.
        """
        if not case.tests:
            return ReferenceTestsResult(
                status="not_available",
                case_id=case.case_id,
                reason="The reference case has no tests.",
            )
        info = self.info()
        if not info.enabled:
            return ReferenceTestsResult(status="not_run", case_id=case.case_id, reason=info.reason)
        refused = self._refuse(case, candidate_code, timeout_s)
        if refused is not None:
            return refused
        problems = policy.admission_problems(candidate_code)
        if problems == ["syntax_error"]:
            total = len(case.tests)
            return ReferenceTestsResult(
                status="fail",
                case_id=case.case_id,
                total=total,
                passed=0,
                failed=total,
                errored=0,
                reason="The candidate does not parse, so the function cannot be defined.",
                duration_s=0.0,
                failures=[
                    ReferenceTestFailure(
                        index=0, kind="missing_function", detail=_syntax_detail(candidate_code)
                    )
                ],
            )
        if problems:
            texts = "; ".join(policy.describe(code) for code in problems[:5])
            return ReferenceTestsResult(
                status="not_run",
                case_id=case.case_id,
                reason=_bounded(f"The candidate was not executed (runner policy): {texts}"),
            )
        wall = self.limits.wall_timeout_s
        budget_limited = timeout_s is not None and timeout_s < wall
        if budget_limited:
            wall = timeout_s
        execution = self._execute(
            case.function_name,
            candidate_code,
            case.tests,
            wall_s=wall,
            cpu_s=self.limits.cpu_time_s,
            memory_mb=self.limits.memory_mb,
        )
        return _to_result(case, execution, wall, self.limits, budget_limited=budget_limited)

    # --- Execution --------------------------------------------------------------------

    def _refuse(
        self, case: ReferenceCase, candidate: str, timeout_s: float | None
    ) -> ReferenceTestsResult | None:
        if timeout_s is not None and timeout_s <= 0:
            return ReferenceTestsResult(
                status="not_run",
                case_id=case.case_id,
                reason="No time was left in the run for reference tests.",
            )
        if len(candidate) > self.limits.max_candidate_chars:
            return ReferenceTestsResult(
                status="not_run",
                case_id=case.case_id,
                reason=(
                    f"The candidate exceeds {self.limits.max_candidate_chars} characters and "
                    "was not executed."
                ),
            )
        problem = None
        if case.task_type != guard_clauses.TASK_TYPE:
            problem = f"Reference cases of task type {case.task_type!r} are not supported."
        elif not case.function_name.isidentifier():
            problem = "The reference case names an invalid function."
        elif len(case.tests) > self.limits.max_tests:
            problem = f"The reference case has more than {self.limits.max_tests} tests."
        if problem is None:
            return None
        return ReferenceTestsResult(status="error", case_id=case.case_id, reason=problem)

    def _execute(
        self,
        function_name: str,
        source: str,
        tests: list[ReferenceTest],
        *,
        wall_s: float,
        cpu_s: float,
        memory_mb: int,
        audit_hook: bool = True,
    ) -> Execution:
        """Run one test process. Used by run() after admission and by the self-checks."""
        nonce = secrets.token_hex(16)
        try:
            workdir = tempfile.mkdtemp(prefix="refactor-ai-runner-", dir=self._work_root)
        except OSError as exc:  # for example a full disk
            logger.error("The runner could not create its working directory: %s", exc)
            execution = Execution(
                outcome="start_failed", workdir_removed=True, detail=f"workdir: {exc}"
            )
            self.last_execution = execution
            return execution
        payload = json.dumps(
            {
                "v": runner_child.PROTOCOL_VERSION,
                "nonce": nonce,
                "function": function_name,
                "source": source,
                "tests": [
                    {
                        "args": test.args,
                        "kwargs": test.kwargs,
                        "kind": test.expect.kind,
                        "value": test.expect.value,
                        "exception": test.expect.exception,
                    }
                    for test in tests
                ],
                "limits": {"memory_bytes": memory_mb * 1024 * 1024, "cpu_seconds": cpu_s},
                "workdir": workdir,
            }
        ).encode("utf-8")
        command = [self.interpreter, "-I", "-S", "-B", "-X", "utf8", str(CHILD_SCRIPT)]
        if not audit_hook:
            command.append(runner_child.NO_HOOK_FLAG)
        try:
            if len(payload) > self.limits.max_payload_bytes:
                execution = Execution(outcome="start_failed", detail="payload too large")
            elif sys.platform == "win32":
                execution = self._run_windows(command, payload, workdir, wall_s, cpu_s, memory_mb)
            else:
                execution = self._run_posix(command, payload, workdir, wall_s)
        except Exception as exc:  # a runner fault must become a result, not an exception
            logger.exception("The reference test process failed")
            execution = Execution(outcome="start_failed", detail=type(exc).__name__)
        finally:
            removed = _remove_tree(workdir)
        execution.workdir = workdir
        execution.workdir_removed = removed
        execution.events = _parse_events(execution.raw_stdout, nonce)
        if sys.platform != "win32":
            ready = execution.first("ready") or {}
            execution.isolation_applied = ready.get("limits") == "rlimit"
        self.last_execution = execution
        return execution

    def _run_windows(
        self,
        command: list[str],
        payload: bytes,
        workdir: str,
        wall_s: float,
        cpu_s: float,
        memory_mb: int,
    ) -> Execution:
        from refactor_ai.verification import _winjob

        job = _winjob.JobObject(memory_bytes=memory_mb * 1024 * 1024, cpu_seconds=cpu_s)
        try:
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=workdir,
                    env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")},
                    creationflags=_winjob.CREATE_SUSPENDED | _winjob.DETACHED_PROCESS,
                    close_fds=True,
                )
            except OSError as exc:
                return Execution(outcome="start_failed", detail=f"start: {exc}")
            started = time.monotonic()
            try:
                job.assign(process.pid)
                _winjob.resume_process(process.pid)
            except OSError as exc:
                # Never let the process run outside the job: kill it while suspended.
                process.kill()
                _reap(process)
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
                return Execution(outcome="start_failed", pid=process.pid, detail=f"job: {exc}")
            io = _BoundedIO(
                process, payload, self.limits.max_output_bytes, self.limits.max_stderr_bytes
            )
            io.start()
            timed_out = False
            try:
                process.wait(timeout=wall_s)
            except subprocess.TimeoutExpired:
                timed_out = True
            job.terminate(1)
            reaped = _reap(process)
            streams_closed = io.join(5.0)
            elapsed = time.monotonic() - started
            _total, _active, killed_by_limit = job.accounting()
            empty = job.wait_until_empty(5.0)
            exit_code = process.returncode
            unsigned = None if exit_code is None else exit_code & 0xFFFFFFFF
            if timed_out:
                outcome = "timeout"
            elif killed_by_limit or unsigned == _winjob.STATUS_QUOTA_EXCEEDED:
                outcome = "cpu_limit"
            elif io.overflow:
                outcome = "output_overflow"
            else:
                outcome = "completed"
            return Execution(
                outcome=outcome,
                raw_stdout=bytes(io.stdout),
                exit_code=exit_code,
                elapsed_s=elapsed,
                stderr=io.stderr.decode("utf-8", errors="replace"),
                pid=process.pid,
                isolation_applied=True,
                cleanup_ok=reaped and empty and streams_closed,
                peak_memory_bytes=job.peak_process_memory(),
            )
        finally:
            job.close()

    def _run_posix(
        self, command: list[str], payload: bytes, workdir: str, wall_s: float
    ) -> Execution:
        drop = privilege_drop()
        if drop:
            try:
                os.chown(workdir, UNPRIVILEGED_ID, UNPRIVILEGED_ID)
            except OSError as exc:
                return Execution(outcome="start_failed", detail=f"workdir owner: {exc}")
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                env={},
                start_new_session=True,
                close_fds=True,
                **drop,
            )
        except OSError as exc:
            return Execution(outcome="start_failed", detail=f"start: {exc}")
        started = time.monotonic()
        io = _BoundedIO(
            process, payload, self.limits.max_output_bytes, self.limits.max_stderr_bytes
        )
        io.start()
        timed_out = False
        try:
            process.wait(timeout=wall_s)
        except subprocess.TimeoutExpired:
            timed_out = True
        _kill_group(process.pid)
        reaped = _reap(process)
        streams_closed = io.join(5.0)
        elapsed = time.monotonic() - started
        exit_code = process.returncode
        if timed_out:
            outcome = "timeout"
        elif hasattr(signal, "SIGXCPU") and exit_code == -int(signal.SIGXCPU):
            outcome = "cpu_limit"
        elif io.overflow:
            outcome = "output_overflow"
        else:
            outcome = "completed"
        return Execution(
            outcome=outcome,
            raw_stdout=bytes(io.stdout),
            exit_code=exit_code,
            elapsed_s=elapsed,
            stderr=io.stderr.decode("utf-8", errors="replace"),
            pid=process.pid,
            cleanup_ok=reaped and streams_closed and _group_empty(process.pid),
        )

    # --- Self-checks ------------------------------------------------------------------

    def _compute_info(self) -> RunnerInfo:
        if not self._configured:
            return RunnerInfo(enabled=False, reason=self._disabled_reason, isolation={})
        if sys.platform not in SUPPORTED_PLATFORMS:
            return RunnerInfo(
                enabled=False,
                reason=f"Reference test execution is not supported on {sys.platform}.",
                isolation={"platform_supported": False},
            )
        try:
            checks = run_self_checks(self)
        except Exception:
            logger.exception("The runner isolation self-checks raised")
            return RunnerInfo(
                enabled=False,
                reason="The isolation self-checks could not complete; execution is disabled.",
                isolation={"self_checks_completed": False},
            )
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            logger.warning("Runner isolation self-checks failed: %s", ", ".join(failed))
            return RunnerInfo(
                enabled=False,
                reason=(
                    "Isolation self-checks failed: " + ", ".join(failed) + ". Reference test "
                    "execution is disabled."
                ),
                isolation=checks,
            )
        return RunnerInfo(enabled=True, reason=None, isolation=checks)


def _syntax_detail(candidate: str) -> str:
    try:
        ast.parse(candidate)
    except SyntaxError as exc:
        return _bounded(f"The candidate does not parse: {exc.msg} (line {exc.lineno}).")
    except (ValueError, RecursionError, MemoryError) as exc:
        return _bounded(f"The candidate does not parse ({type(exc).__name__}).")
    return "The candidate does not parse."


def _limit_text(execution: Execution, wall_s: float, limits: RunnerLimits) -> str:
    if execution.outcome == "cpu_limit":
        return f"exceeded the {limits.cpu_time_s:g} s CPU time limit"
    return f"did not finish within the {wall_s:g} s wall-clock limit"


def _to_result(
    case: ReferenceCase,
    execution: Execution,
    wall_s: float,
    limits: RunnerLimits,
    *,
    budget_limited: bool = False,
) -> ReferenceTestsResult:
    """Map one test process to the contract result. Missing evidence is never a pass.

    Counts cover the tests that ran; when a timeout stops the process, later tests are not
    run and total exceeds passed + failed + errored. budget_limited means wall_s is the
    time left in the workflow run, below the runner's own limit: a wall-clock timeout then
    ends the run's budget, not the candidate's, and is not_run (the disposition is
    uncertain) unless failures or errors already observed decide the result.
    """
    total = len(case.tests)
    base = {"case_id": case.case_id, "total": total, "duration_s": round(execution.elapsed_s, 4)}
    budget_ended = budget_limited and execution.outcome == "timeout"

    def error(reason: str, failures=None, **counts) -> ReferenceTestsResult:
        return ReferenceTestsResult(
            status="error", reason=_bounded(reason), failures=failures or [], **base, **counts
        )

    def stopped(where: str) -> str:
        return (
            f"The run's time limit left only {wall_s:.3g} s for the reference tests, and "
            f"they stopped {where}."
        )

    def not_run(where: str) -> ReferenceTestsResult:
        return ReferenceTestsResult(status="not_run", reason=_bounded(stopped(where)), **base)

    if execution.outcome == "start_failed":
        return error("The isolated test process could not be started.")
    if execution.outcome == "output_overflow":
        return error("The test process wrote more output than the runner accepts.")
    fatal = execution.first("fatal")
    if fatal is not None:
        return error(f"The test process refused to run: {fatal.get('d') or 'setup failed'}.")
    if execution.first("ready") is None:
        if budget_ended:
            return not_run("before the test process was ready")
        if execution.outcome in ("timeout", "cpu_limit"):
            limit = _limit_text(execution, wall_s, limits)
            return error(f"The test process {limit} before it was ready.")
        return error(
            f"The test process stopped before it was ready (exit code {execution.exit_code})."
        )

    defined = execution.first("defined")
    if defined is not None and not defined.get("ok"):
        detail = _bounded(defined.get("d") or "The function under test is not defined.")
        return ReferenceTestsResult(
            status="fail",
            reason="The candidate does not define the function under test.",
            passed=0,
            failed=total,
            errored=0,
            failures=[ReferenceTestFailure(index=0, kind="missing_function", detail=detail)],
            **base,
        )

    results = execution.tests()
    failures: list[ReferenceTestFailure] = []
    passed = failed = errored = 0
    for position, event in enumerate(results):
        kind = event.get("k")
        if event.get("i") != position:
            return error("The test process reported tests out of order.")
        if kind == "pass":
            passed += 1
            continue
        if kind in CANDIDATE_FAILURES:
            failed += 1
        elif kind in ERROR_KINDS:
            errored += 1
        else:
            return error("The test process reported an unknown outcome.")
        if len(failures) < MAX_FAILURES:
            failures.append(
                ReferenceTestFailure(
                    index=position, kind=kind, detail=_bounded(event.get("d") or kind)
                )
            )

    finished = execution.first("final") is not None
    if budget_ended and not finished:
        # More tests could not change a failure or an error that already happened.
        if failed:
            text = f"{failed} of {total} reference tests failed. " + stopped(
                f"after {len(results)} of {total} tests"
            )
            return ReferenceTestsResult(
                status="fail",
                reason=_bounded(text),
                passed=passed,
                failed=failed,
                errored=errored,
                failures=failures,
                **base,
            )
        if errored:
            text = f"{errored} of {total} reference tests could not be evaluated. " + stopped(
                f"after {len(results)} of {total} tests"
            )
            return error(text, failures, passed=passed, failed=failed, errored=errored)
        if defined is None:
            return not_run("while the function was being defined")
        if not results:
            return not_run("before the first test finished")
        return not_run(f"after {passed} of {total} tests had passed")

    if execution.outcome in ("timeout", "cpu_limit") and not finished:
        limit = _limit_text(execution, wall_s, limits)
        if defined is None:
            text = f"Defining the function {limit}; none of the {total} tests ran."
            return ReferenceTestsResult(
                status="fail",
                reason=_bounded(text),
                passed=0,
                failed=total,
                errored=0,
                failures=[ReferenceTestFailure(index=0, kind="timeout", detail=_bounded(text))],
                **base,
            )
        index = min(len(results), total - 1)
        text = f"Test {index} {limit}."
        later = total - index - 1
        if later > 0:
            text += f" {later} later tests were not run."
        if len(failures) < MAX_FAILURES:
            failures.append(
                ReferenceTestFailure(index=index, kind="timeout", detail=_bounded(text))
            )
        return ReferenceTestsResult(
            status="fail",
            reason=_bounded(text),
            passed=passed,
            failed=failed + 1,
            errored=errored,
            failures=failures,
            **base,
        )

    if not finished or defined is None or len(results) != total:
        memory_note = ""
        peak = execution.peak_memory_bytes
        if peak is not None and peak >= 0.9 * limits.memory_mb * 1024 * 1024:
            memory_note = " The memory limit was reached."
        where = "while defining the function" if defined is None else f"during test {len(results)}"
        text = (
            f"The test process ended unexpectedly (exit code {execution.exit_code}) "
            f"{where}.{memory_note}"
        )
        if len(failures) < MAX_FAILURES:
            failures.append(
                ReferenceTestFailure(
                    index=min(len(results), total - 1), kind="runner_error", detail=_bounded(text)
                )
            )
        return error(text, failures, passed=passed, failed=failed, errored=errored + 1)

    if passed == total:
        status, reason = "pass", None
    elif failed:
        status, reason = "fail", f"{failed} of {total} reference tests failed."
    else:
        status, reason = "error", f"{errored} of {total} reference tests could not be evaluated."
    return ReferenceTestsResult(
        status=status,
        reason=reason,
        passed=passed,
        failed=failed,
        errored=errored,
        failures=failures,
        **base,
    )


# --- Isolation self-checks ------------------------------------------------------------

# Probe functions for the self-checks. They run only inside the isolated test process,
# where every attempted operation (network, file writes, os.system, subprocess, ctypes,
# frame access) must be refused by the audit hook; a probe that succeeds fails its check
# and keeps execution disabled. Nothing here runs in the calling process.
PROBE_SOURCE = """
def probe(kind, target):
    if kind == "network":
        import socket
        connection = socket.create_connection(("127.0.0.1", target), timeout=3)
        connection.close()
        return "connected"
    if kind == "raw_socket":
        import _socket
        return "imported"
    if kind == "write":
        import io
        handle = io.open(target, "w")
        handle.write("written")
        handle.close()
        return "written"
    if kind == "os_write":
        import os
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(descriptor)
        return "written"
    if kind == "read":
        import io
        handle = io.open(target)
        data = handle.read()
        handle.close()
        return data
    if kind == "subprocess":
        import subprocess
        subprocess.run(target)
        return "spawned"
    if kind == "system":
        import os
        os.system(target)
        return "spawned"
    if kind == "ctypes":
        import ctypes
        return "loaded"
    if kind == "frames":
        import sys
        return sys._getframe(1).f_code.co_name
    return "unknown probe"
"""

BASIC_SOURCE = """
def basic(value, scale=1):
    if value is None:
        raise ValueError("value is required")
    if value < 0:
        return -value * scale
    return value * scale
"""

MEMORY_SOURCE = """
def allocate(size):
    return len(bytearray(size))
"""

SPIN_SOURCE = """
def spin():
    count = 0
    while True:
        count += 1
"""


def _returns(args: str, value: str, kwargs: str = "{}") -> ReferenceTest:
    return ReferenceTest(args=args, kwargs=kwargs, expect={"kind": "return", "value": value})


def _raises(args: str, exception: str) -> ReferenceTest:
    return ReferenceTest(args=args, expect={"kind": "raise", "exception": exception})


def _outcomes(execution: Execution) -> dict[int, tuple[str, str]]:
    return {
        event["i"]: (str(event.get("k")), str(event.get("d") or ""))
        for event in execution.tests()
        if isinstance(event.get("i"), int)
    }


def _blocked(outcome: tuple[str, str] | None) -> bool:
    """The probe raised the runner's policy error instead of doing what it attempted."""
    return (
        outcome is not None
        and outcome[0] == "unexpected_exception"
        and "RunnerPolicyError" in outcome[1]
    )


def run_self_checks(runner: SubprocessReferenceRunner) -> dict[str, bool]:
    """Exercise every isolation layer with probes; each entry must be True to enable."""
    limits = runner.limits
    wall = max(limits.wall_timeout_s, 10.0)
    checks: dict[str, bool] = {
        "platform_supported": sys.platform in SUPPORTED_PLATFORMS,
        "interpreter_found": os.path.isfile(runner.interpreter),
    }

    # 1. Basic execution, environment, working directory and cleanup.
    basic = runner._execute(
        "basic",
        BASIC_SOURCE,
        [
            _returns("[3]", "3"),
            _returns("[-2]", "2"),
            _returns("[4]", "8", kwargs="{'scale': 2}"),
            _raises("[None]", "ValueError"),
        ],
        wall_s=wall,
        cpu_s=limits.cpu_time_s,
        memory_mb=limits.memory_mb,
    )
    outcomes = _outcomes(basic)
    ready = basic.first("ready") or {}
    environment = ready.get("env")
    checks["basic_execution"] = basic.outcome == "completed" and all(
        outcomes.get(index, ("", ""))[0] == "pass" for index in range(4)
    )
    checks["os_limits_applied"] = basic.isolation_applied
    checks["audit_hook_installed"] = ready.get("hook") is True
    checks["environment_scrubbed"] = (
        isinstance(environment, list) and set(environment) <= ALLOWED_CHILD_ENVIRONMENT
    )
    checks["working_directory_isolated"] = ready.get("cwd_ok") is True
    checks["workdir_removed"] = basic.workdir_removed

    # 2. Audit-hook layer: network, files, processes, native code and frames.
    probe_dir = tempfile.mkdtemp(prefix="refactor-ai-probe-", dir=runner._work_root)
    listener = None
    try:
        secret = Path(probe_dir, "secret.txt")
        secret.write_text(secrets.token_hex(8), encoding="utf-8")
        write_target = Path(probe_dir, "written.txt")
        os_write_target = Path(probe_dir, "os-written.txt")
        marker = Path(probe_dir, "spawned.txt")
        port = 9
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.setblocking(False)
            port = listener.getsockname()[1]
        except OSError:
            listener = None
        spawn = [runner.interpreter, "-c", f"open({str(marker)!r}, 'w').close()"]
        hooked = runner._execute(
            "probe",
            PROBE_SOURCE,
            [
                _returns(repr(["network", port]), "'connected'"),
                _returns(repr(["raw_socket", None]), "'imported'"),
                _returns(repr(["write", str(write_target)]), "'written'"),
                _returns(repr(["os_write", str(os_write_target)]), "'written'"),
                _returns(repr(["read", str(secret)]), "''"),
                _returns(repr(["subprocess", spawn]), "'spawned'"),
                _returns(repr(["system", "exit 0"]), "'spawned'"),
                _returns(repr(["ctypes", None]), "'loaded'"),
                _returns(repr(["frames", None]), "''"),
            ],
            wall_s=wall,
            cpu_s=limits.cpu_time_s,
            memory_mb=limits.memory_mb,
        )
        probe = _outcomes(hooked)
        connected = False
        if listener is not None:
            try:
                connection, _ = listener.accept()
                connection.close()
                connected = True
            except OSError:
                connected = False
        checks["network_blocked"] = (
            _blocked(probe.get(0)) and _blocked(probe.get(1)) and not connected
        )
        checks["file_write_blocked"] = (
            _blocked(probe.get(2))
            and _blocked(probe.get(3))
            and not write_target.exists()
            and not os_write_target.exists()
        )
        checks["host_read_blocked"] = _blocked(probe.get(4))
        checks["subprocess_blocked"] = (
            _blocked(probe.get(5)) and _blocked(probe.get(6)) and not marker.exists()
        )
        checks["native_code_blocked"] = _blocked(probe.get(7))
        checks["introspection_blocked"] = _blocked(probe.get(8))

        # 3. Operating-system process limit, verified with the audit hook switched off.
        unhooked = runner._execute(
            "probe",
            PROBE_SOURCE,
            [_returns(repr(["subprocess", spawn]), "'spawned'")],
            wall_s=wall,
            cpu_s=limits.cpu_time_s,
            memory_mb=limits.memory_mb,
            audit_hook=False,
        )
        outcome = _outcomes(unhooked).get(0)
        checks["process_limit_enforced"] = (
            unhooked.outcome == "completed"
            and (unhooked.first("ready") or {}).get("hook") is False
            and outcome is not None
            and outcome[0] == "unexpected_exception"
            and not marker.exists()
        )
    finally:
        if listener is not None:
            listener.close()
        shutil.rmtree(probe_dir, ignore_errors=True)

    # 4. Memory limit: one allocation above the limit must fail inside the process.
    over = (limits.memory_mb + 64) * 1024 * 1024
    memory = runner._execute(
        "allocate",
        MEMORY_SOURCE,
        [_returns(f"[{over}]", str(over))],
        wall_s=wall,
        cpu_s=limits.cpu_time_s,
        memory_mb=limits.memory_mb,
    )
    outcome = _outcomes(memory).get(0)
    checks["memory_limit_enforced"] = (
        outcome is not None and outcome[0] == "unexpected_exception" and "MemoryError" in outcome[1]
    )

    # 5. Wall-clock timeout and process cleanup.
    started = time.monotonic()
    spun = runner._execute(
        "spin",
        SPIN_SOURCE,
        [_returns("[]", "None")],
        wall_s=1.0,
        cpu_s=60.0,
        memory_mb=limits.memory_mb,
    )
    checks["timeout_enforced"] = spun.outcome == "timeout" and time.monotonic() - started < 16.0
    checks["process_cleanup"] = spun.cleanup_ok and basic.cleanup_ok and spun.workdir_removed

    # 6. CPU-time limit. The probe normally ends after about 1-3 s; the long wall-clock
    # allowance only keeps a busy machine (little CPU share) from failing the check.
    burned = runner._execute(
        "spin",
        SPIN_SOURCE,
        [_returns("[]", "None")],
        wall_s=60.0,
        cpu_s=1.0,
        memory_mb=limits.memory_mb,
    )
    checks["cpu_limit_enforced"] = burned.outcome == "cpu_limit" and burned.cleanup_ok
    return checks


def create_runner(mode: str = "auto", **kwargs) -> SubprocessReferenceRunner:
    """The service's runner factory. mode "disabled" never executes anything."""
    if mode not in ("auto", "disabled"):
        raise ValueError("mode must be 'auto' or 'disabled'")
    return SubprocessReferenceRunner(enabled=mode == "auto", **kwargs)

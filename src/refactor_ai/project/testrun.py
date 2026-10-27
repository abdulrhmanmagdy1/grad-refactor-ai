"""Running a project's own tests before and after a fix (off unless the user enables it).

The tests run with pytest in a separate interpreter on a fresh copy of the project, with
limits: a wall-clock limit; on Windows a Job Object with memory and CPU-time limits and a
single process; on Linux resource limits, a new session and, when the service runs as root,
an unprivileged user. An audit hook installed before pytest starts refuses network access,
new processes, and writes or deletions outside the copy; TEMP points into the copy and no
bytecode is written. The environment is empty except for what Python needs.

This executes the user's own code. Like the reference runner, it is a hardening layer and
not a sandbox for hostile code (docs/development/runner-safety.md); it is meant for the
user's own projects.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path

WALL_S = 180.0
CPU_S = 150.0
MEMORY_MB = 1536
REPORT_FILE = "pytest-report.xml"

# Runs inside the test process before pytest. argv[1] is the project copy; any further
# arguments are test paths inside it (default: the whole copy).
BOOTSTRAP = (
    r"""
import os, sys
ROOT = os.path.realpath(sys.argv[1])
TARGETS = [os.path.join(ROOT, target) for target in sys.argv[2:]] or [ROOT]
BLOCKED = ("socket.connect", "socket.connect_ex", "socket.bind", "socket.sendto",
           "socket.getaddrinfo", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
           "os.spawn", "os.startfile", "os.fork", "os.forkpty", "ctypes.dlopen")
WRITES = ("os.remove", "os.unlink", "os.rmdir", "os.rename", "os.replace", "os.mkdir",
          "shutil.rmtree", "shutil.move", "os.truncate", "os.chmod")

NULL_DEVICES = {os.devnull.lower(), "nul", "\\\\.\\nul", "/dev/null"}

def inside(path):
    try:
        raw = os.fspath(path)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if raw.lower() in NULL_DEVICES:
            return True
        real = os.path.realpath(raw)
    except (TypeError, ValueError, OSError):
        return False
    return real == ROOT or real.startswith(ROOT + os.sep)

def hook(event, args):
    if event in BLOCKED or event.startswith("os.exec") or event.startswith("os.spawn"):
        raise PermissionError(f"blocked by the project test runner: {event}")
    if event == "open" and args:
        path, mode = args[0], args[1] if len(args) > 1 else "r"
        flags = args[2] if len(args) > 2 else 0
        writing = isinstance(mode, str) and any(c in mode for c in "wax+")
        mask = os.O_WRONLY | os.O_RDWR | os.O_CREAT
        writing = writing or bool(isinstance(flags, int) and flags & mask)
        if writing and isinstance(path, (str, bytes, os.PathLike)) and not inside(path):
            raise PermissionError(f"blocked by the project test runner: writing {path!r}")
    elif event in WRITES and args:
        for path in args[:2]:
            if isinstance(path, (str, bytes, os.PathLike)) and not inside(path):
                raise PermissionError(f"blocked by the project test runner: {event} {path!r}")

# pytest and its terminal output load first (on Windows they open system DLLs through ctypes);
# the hook is in place before any project code is imported.
import pytest
import _pytest.terminal
try:
    import colorama
    colorama.just_fix_windows_console()
except Exception:
    pass
sys.addaudithook(hook)
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "-o", "addopts=", "--rootdir", ROOT,
                      "--junitxml", os.path.join(ROOT, "__REPORT__"), *TARGETS]))
"""
).replace("__REPORT__", REPORT_FILE)


@dataclass
class TestReport:
    """Outcome of one test run: per-test results when the run produced a report."""

    __test__ = False  # not a pytest test class

    status: str  # "ran", "no_tests", "error", "timeout"
    passed: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    errors: set[str] = field(default_factory=set)
    # Failure or error text per failing test, bounded.
    messages: dict[str, str] = field(default_factory=dict)
    skipped: int = 0
    duration_s: float = 0.0
    detail: str = ""

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed) + len(self.errors)

    def summary(self) -> dict:
        return {
            "status": self.status,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "errors": len(self.errors),
            "skipped": self.skipped,
            "duration_s": round(self.duration_s, 2),
            "detail": self.detail,
        }


def compare(baseline: TestReport, after: TestReport) -> tuple[str, str]:
    """(status, detail) of a fix's test check: tests that passed before must still pass."""
    if after.status == "timeout":
        return "fail", "The tests did not finish in time after the fix."
    if after.status != "ran":
        return "error", after.detail or "The tests could not run after the fix."
    broken = sorted(baseline.passed - after.passed)
    if broken:
        shown = ", ".join(broken[:5]) + (" ..." if len(broken) > 5 else "")
        return "fail", f"{len(broken)} test(s) that passed before now fail: {shown}"
    newly = sorted(after.passed - baseline.passed)
    detail = f"{len(after.passed)} passed, none broken"
    if newly:
        detail += f"; {len(newly)} test(s) fail before the fix and pass after it"
    return "pass", detail + "."


MAX_REPORT_BYTES = 5_000_000


MAX_MESSAGE = 800


def _failure_text(element) -> str:
    """pytest's message and the end of its traceback (where the assertion is)."""
    message = element.get("message", "") or ""
    text = (element.text or "").strip()
    tail = text[-(MAX_MESSAGE // 2) :] if text else ""
    combined = message if not tail or tail in message else f"{message}\n{tail}"
    return combined[:MAX_MESSAGE]


def parse_report(path: Path) -> TestReport | None:
    """pytest's JUnit XML report. The project's own code could rewrite this file, so it is
    size-limited and may not declare a DTD or entities."""
    try:
        if path.stat().st_size > MAX_REPORT_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        return None
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return None
    report = TestReport(status="ran")
    for case in root.iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("skipped") is not None:
            report.skipped += 1
        elif case.find("failure") is not None:
            report.failed.add(name)
            report.messages[name] = _failure_text(case.find("failure"))
        elif case.find("error") is not None:
            report.errors.add(name)
            report.messages[name] = _failure_text(case.find("error"))
        else:
            report.passed.add(name)
    return report


def _text(stdout: bytes, stderr: bytes) -> str:
    """The run's output for error details, bounded."""
    text = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
    return text[-20_000:]


def _environment(copy: Path) -> dict[str, str]:
    temp = copy / ".tmp"
    temp.mkdir(exist_ok=True)
    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "TEMP": str(temp),
        "TMP": str(temp),
        "TMPDIR": str(temp),
    }
    if os.name == "nt":
        environment["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return environment


class ProjectTestRunner:
    """Runs pytest on copies of a project with limits; one run at a time."""

    def __init__(self, *, wall_s: float = WALL_S, cpu_s: float = CPU_S, memory_mb: int = MEMORY_MB):
        self.wall_s = wall_s
        self.cpu_s = cpu_s
        self.memory_mb = memory_mb

    def run(
        self,
        root: Path,
        replacements: dict[str, str] | None = None,
        targets: tuple[str, ...] = (),
    ) -> TestReport:
        """Copy `root`, write `replacements` (relative path -> text) into the copy, run tests
        (only the `targets`, relative test paths, when given)."""
        with tempfile.TemporaryDirectory(prefix="project-tests-") as temp:
            copy = Path(temp) / "project"
            shutil.copytree(root, copy)
            for relative in (*(replacements or {}), *targets):
                if not (copy / relative).resolve().is_relative_to(copy.resolve()):
                    raise ValueError(f"path outside the project: {relative}")
            for relative, text in (replacements or {}).items():
                (copy / relative).write_text(text, encoding="utf-8", newline="")
            return self._run_copy(copy, targets)

    def _run_copy(self, copy: Path, targets: tuple[str, ...] = ()) -> TestReport:
        command = [sys.executable, "-X", "utf8", "-c", BOOTSTRAP, str(copy), *targets]
        started = time.monotonic()
        try:
            exit_code, timed_out, output = self._execute(command, copy)
        except OSError as exc:
            return TestReport(status="error", detail=f"The tests could not start: {exc}")
        duration = time.monotonic() - started
        if timed_out:
            return TestReport(status="timeout", duration_s=duration, detail="Time limit reached.")
        report = parse_report(copy / REPORT_FILE)
        if exit_code == 5:  # pytest: no tests collected
            return TestReport(status="no_tests", duration_s=duration, detail="No tests collected.")
        if report is None:
            lines = [line for line in output.splitlines() if line.strip()]
            errors = [line for line in lines if "Error" in line] or lines
            detail = errors[-1].strip() if errors else f"exit code {exit_code}"
            return TestReport(status="error", duration_s=duration, detail=detail[:300])
        report.duration_s = duration
        if exit_code not in (0, 1):
            report.detail = f"pytest exit code {exit_code}"
        return report

    def _execute(self, command: list[str], copy: Path) -> tuple[int | None, bool, str]:
        environment = _environment(copy)
        if os.name == "nt":
            from refactor_ai.verification import _winjob

            # A virtual environment's python.exe is a launcher that starts the base
            # interpreter as its child, so the job then needs two process slots.
            base = getattr(sys, "_base_executable", None) or sys.executable
            launcher = os.path.normcase(os.path.abspath(base)) != os.path.normcase(
                os.path.abspath(sys.executable)
            )
            job = _winjob.JobObject(
                memory_bytes=self.memory_mb * 1024 * 1024,
                cpu_seconds=self.cpu_s,
                active_processes=2 if launcher else 1,
            )
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=copy,
                    env=environment,
                    # A console without a window: a detached process would make the
                    # launcher's child open a new, visible console window.
                    creationflags=_winjob.CREATE_SUSPENDED | subprocess.CREATE_NO_WINDOW,
                )
                try:
                    job.assign(process.pid)
                    _winjob.resume_process(process.pid)
                except OSError:
                    process.kill()
                    process.communicate()
                    raise
                try:
                    stdout, stderr = process.communicate(timeout=self.wall_s)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    job.terminate(1)
                    stdout, stderr = process.communicate()
                    timed_out = True
                return process.returncode, timed_out, _text(stdout, stderr)
            finally:
                job.terminate(1)
                job.close()
        return self._execute_posix(command, copy, environment)

    def _execute_posix(
        self, command: list[str], copy: Path, environment: dict[str, str]
    ) -> tuple[int | None, bool, str]:
        import resource
        import signal

        from refactor_ai.verification.runner import UNPRIVILEGED_ID, privilege_drop

        drop = privilege_drop()
        if drop:
            for path in [copy, *copy.rglob("*")]:
                os.chown(path, UNPRIVILEGED_ID, UNPRIVILEGED_ID)
            # The temporary folder above the copy is private to root; the unprivileged
            # user may pass through it (not list it) to reach the copy.
            os.chmod(copy.parent, 0o711)
        memory = self.memory_mb * 1024 * 1024
        cpu = int(self.cpu_s)

        def limits() -> None:
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))

        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=copy,
            env=environment,
            start_new_session=True,
            preexec_fn=limits,  # noqa: PLW1509 - only setrlimit, before exec
            **drop,
        )
        try:
            stdout, stderr = process.communicate(timeout=self.wall_s)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            timed_out = True
        return process.returncode, timed_out, _text(stdout, stderr)

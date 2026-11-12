"""Isolated Test Runner for Sandboxed Verification (FR04, NFR01, NFR02).

Strictly isolates execution of candidate code and test cases:
- Never executes code within the API process (NFR01).
- Runs in a separate subprocess with CPU, memory, timeout, environment,
  path, and network restrictions on both Windows and POSIX (NFR02).
- Optionally writes a trusted ``reference.py`` (the original implementation)
  so golden equivalence tests can compare candidate vs baseline behaviour.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, Field

# Non-secret operating-system variables required for an interpreter to start and
# locate its own standard library / site-packages. Secret material (tokens, keys,
# credentials, host paths) is intentionally excluded (NFR02).
_ENV_ALLOWLIST = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "APPDATA",
    "LOCALAPPDATA",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PROCESSOR_ARCHITECTURE",
    "LANG",
    "LC_ALL",
)

# Conftest injected into every sandbox workspace: denies outbound IP sockets
# before user code is imported (NFR02).  AF_UNIX sockets stay available, and
# the socketpair wrapper temporarily permits the internal loopback connection
# that Windows' emulated socketpair performs, so asyncio event loops still
# start without opening a gap for user code.
_NETWORK_GATE = '''"""Sandbox network gate (NFR02): outbound IP sockets are denied.

AF_UNIX sockets stay available. `socket.socketpair()` is wrapped so the
loopback connection used by the emulated Windows implementation is allowed
while user-initiated connections remain blocked.
"""

import socket as _socket

_original_connect = _socket.socket.connect
_original_connect_ex = _socket.socket.connect_ex
_original_socketpair = _socket.socketpair
_denied_families = {_socket.AF_INET, _socket.AF_INET6}
_in_socketpair = False

_MESSAGE = "Network access is disabled inside the isolated sandbox (NFR02)."


def _denied_connect(self, address):
    if not _in_socketpair and self.family in _denied_families:
        raise PermissionError(_MESSAGE)
    return _original_connect(self, address)


def _denied_connect_ex(self, address):
    if not _in_socketpair and self.family in _denied_families:
        raise PermissionError(_MESSAGE)
    return _original_connect_ex(self, address)


def _permitted_socketpair(*args, **kwargs):
    global _in_socketpair
    _in_socketpair = True
    try:
        return _original_socketpair(*args, **kwargs)
    finally:
        _in_socketpair = False


def _denied_create_connection(address, *args, **kwargs):
    raise PermissionError(_MESSAGE)


_socket.socket.connect = _denied_connect
_socket.socket.connect_ex = _denied_connect_ex
_socket.create_connection = _denied_create_connection
_socket.socketpair = _permitted_socketpair
'''

# Resource limits module (Linux/Unix)
try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]


class SandboxResult(BaseModel):
    """Result of sandboxed code execution."""

    success: bool = Field(..., description="Whether execution passed with zero exit code.")
    exit_code: int = Field(..., description="Process exit code.")
    stdout: str = Field(default="", description="Captured standard output.")
    stderr: str = Field(default="", description="Captured standard error.")
    duration_ms: float = Field(..., description="Execution duration in milliseconds.")
    timed_out: bool = Field(
        default=False, description="Whether execution was terminated due to timeout."
    )
    error_message: str | None = Field(default=None, description="Diagnostic error message.")
    reference_provided: bool = Field(
        default=False, description="Whether a baseline reference module was executed too."
    )


class IsolatedRunner:
    """Subprocess runner enforcing execution boundaries and sandbox isolation."""

    def __init__(
        self,
        timeout_seconds: float = 5.0,
        memory_limit_mb: int = 256,
        cpu_time_limit_sec: int = 5,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.memory_limit_bytes = memory_limit_mb * 1024 * 1024
        self.cpu_time_limit_sec = cpu_time_limit_sec

    def _set_resource_limits(self) -> None:
        """Apply resource limits to the child process before execution (POSIX)."""
        if resource is None:
            return

        try:
            # CPU time limit in seconds
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (self.cpu_time_limit_sec, self.cpu_time_limit_sec + 1),
            )
        except (ValueError, OSError):
            pass

        try:
            # Virtual memory limit (RLIMIT_AS)
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.memory_limit_bytes, self.memory_limit_bytes),
            )
        except (ValueError, OSError):
            pass

    def run_test(
        self,
        candidate_code: str,
        test_code: str,
        timeout: float | None = None,
        reference_code: str | None = None,
    ) -> SandboxResult:
        """Run candidate code against test code in a temporary isolated environment.

        Args:
            candidate_code: The Python code to test (saved as solution.py).
            test_code: Tests importing/using solution (saved as test_solution.py).
            timeout: Optional override for execution timeout.
            reference_code: Optional trusted baseline (saved as reference.py) for
                golden equivalence tests synthesized by the AutoTestSynthesizer.

        Returns:
            SandboxResult with exit code, outputs, and status.
        """
        effective_timeout = timeout or self.timeout_seconds
        start_time = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="sandbox_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            sol_file = tmp_path / "solution.py"
            test_file = tmp_path / "test_solution.py"
            gate_file = tmp_path / "conftest.py"

            sol_file.write_text(candidate_code, encoding="utf-8")
            test_file.write_text(test_code, encoding="utf-8")
            gate_file.write_text(_NETWORK_GATE, encoding="utf-8")
            if reference_code is not None:
                (tmp_path / "reference.py").write_text(reference_code, encoding="utf-8")

            # Minimal sanitized environment: keep only non-secret OS essentials and
            # strip all host tokens/keys/credentials (NFR02).
            sanitized_env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
            sanitized_env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
            sanitized_env["PYTHONPATH"] = str(tmp_path)
            sanitized_env["PYTHONUNBUFFERED"] = "1"
            sanitized_env["PYTHONDONTWRITEBYTECODE"] = "1"
            # Third-party pytest plugins (coverage, cloud tracers, ...) are not
            # needed by the trusted test snippets and can add seconds to every
            # subprocess start, which counts against the 5 s sandbox budget.
            # Disabling autoload also keeps host plugins out of the sandbox
            # (NFR02); pytest's own built-ins remain active.
            sanitized_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

            cmd = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--tb=short",
                str(test_file),
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(tmp_path),
                    env=sanitized_env,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    # POSIX: hard CPU/memory rlimits. Windows: strict wall-clock
                    # timeout in the parent process (rlimits are unavailable).
                    preexec_fn=self._set_resource_limits if os.name != "nt" else None,
                    check=False,
                )
                duration_ms = (time.perf_counter() - start_time) * 1000
                success = proc.returncode == 0

                return SandboxResult(
                    success=success,
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    duration_ms=round(duration_ms, 2),
                    timed_out=False,
                    reference_provided=reference_code is not None,
                    error_message=None
                    if success
                    else f"Tests failed with exit code {proc.returncode}",
                )

            except subprocess.TimeoutExpired as exc:
                duration_ms = (time.perf_counter() - start_time) * 1000
                stdout = (
                    exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                )
                stderr = (
                    exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                )

                return SandboxResult(
                    success=False,
                    exit_code=-1,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=round(duration_ms, 2),
                    timed_out=True,
                    reference_provided=reference_code is not None,
                    error_message=f"Execution timed out after {effective_timeout}s (FR08, NFR02).",
                )
            except Exception as exc:
                duration_ms = (time.perf_counter() - start_time) * 1000
                return SandboxResult(
                    success=False,
                    exit_code=-2,
                    stdout="",
                    stderr=str(exc),
                    duration_ms=round(duration_ms, 2),
                    timed_out=False,
                    reference_provided=reference_code is not None,
                    error_message=f"Sandbox error: {exc}",
                )


# Global instance
sandbox_runner = IsolatedRunner()

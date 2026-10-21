"""Local model provider: the pinned model runs in a separate worker process.

The API and core CI never import PyTorch. LocalProvider starts model_worker.py with the
training environment's interpreter and exchanges JSON lines with it over stdin/stdout
(protocol version 1, documented in model_worker.py). The worker loads the pinned base
model once, plus an optional LoRA adapter; use_adapter selects the adapter per call.

Guarantees (docs/architecture/contracts.md, "Model provider"):

- Expected failures are returned as GenerationResult.error, never raised.
- Calls are serialized by a lock. A call that cannot get the lock within its timeout_s
  returns busy.
- timeout_s bounds each generation request from sending it to receiving the reply. On
  timeout the parent kills its own worker process (only that process) and the next
  call starts a fresh worker. Model loading is bounded separately by load_timeout_s.
- use_adapter=true without a configured adapter returns unavailable, and a configured
  adapter that fails to load is a model_load_error; the base model is never a silent
  fallback.
- Each result reports the exact ModelReference that the worker confirmed after loading.
  elapsed_s is the wall time of the whole call, including any wait for the lock and any
  model load (which also adds a warning); token counts come from the worker.

Configuration file keys (configs/model.example.json): python, model_dir, model_id,
model_revision, adapter_dir, adapter_id, adapter_sha256, adapter_config_sha256, device, dtype,
load_timeout_s. Relative paths are resolved against the directory of the config file.
Keys starting with "_" are comments.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from refactor_ai.contracts import (
    GenerationRequest,
    GenerationResult,
    ModelReference,
    ProviderErrorCode,
    ProviderInfo,
    ProviderMode,
)
from refactor_ai.providers.base import failed_result

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
WORKER_SCRIPT = Path(__file__).with_name("model_worker.py")
SHUTDOWN_GRACE_S = 10.0
KILL_WAIT_S = 15.0
INTERPRETER_EXIT_WAIT_S = 3.0
CLOSE_LOCK_WAIT_S = 1.0
MAX_MESSAGE_CHARS = 500
_WORKER_ERRORS = {
    "input_too_long": ProviderErrorCode.INPUT_TOO_LONG,
    "unavailable": ProviderErrorCode.UNAVAILABLE,
    "generation_error": ProviderErrorCode.GENERATION_ERROR,
}
_PATH_KEYS = ("python", "model_dir", "adapter_dir")


class LocalModelSettings(BaseModel):
    """Settings for LocalProvider, normally read from configs/model.local.json."""

    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    python: Path
    model_dir: Path
    model_id: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    adapter_dir: Path | None = None
    adapter_id: str | None = Field(default=None, min_length=1)
    adapter_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    adapter_config_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    device: Literal["cuda", "cpu"] = "cuda"
    dtype: Literal["bfloat16", "float16", "float32"] = "bfloat16"
    load_timeout_s: float = Field(default=180.0, gt=0.0, le=3600.0)

    @model_validator(mode="after")
    def _adapter_fields_together(self) -> LocalModelSettings:
        if (self.adapter_dir is None) != (self.adapter_id is None):
            raise ValueError("adapter_dir and adapter_id must be set together")
        if self.adapter_sha256 is not None and self.adapter_dir is None:
            raise ValueError("adapter_sha256 requires adapter_dir")
        if self.adapter_config_sha256 is not None and self.adapter_dir is None:
            raise ValueError("adapter_config_sha256 requires adapter_dir")
        return self

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> LocalModelSettings:
        """Read a JSON config; relative paths are resolved against the file's directory.

        Paths are made absolute without following symbolic links: a virtual
        environment's interpreter is often a link to the base interpreter, and only
        the link's own location makes Python use the environment's packages.
        """
        config_path = Path(path)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{config_path.name} must contain a JSON object")
        data = {key: value for key, value in data.items() if not key.startswith("_")}
        base = Path(os.path.abspath(config_path)).parent
        for key in _PATH_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value:
                data[key] = os.path.abspath(base / value)  # base / absolute == absolute
        return cls.model_validate(data)


class _Timeout(Exception):
    pass


class _WorkerGone(Exception):
    pass


class _ProtocolError(Exception):
    pass


class _UnencodableRequest(Exception):
    pass


class _WindowsProcessHandle:
    """An open handle to one Windows process, used to wait for or terminate exactly it.

    Holding the handle keeps Windows from reusing the PID, so terminate() can only ever
    reach the process that was opened.
    """

    _SYNCHRONIZE = 0x00100000
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self, pid: int) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32 = kernel32
        self.pid = pid
        access = (
            self._SYNCHRONIZE | self._PROCESS_TERMINATE | self._PROCESS_QUERY_LIMITED_INFORMATION
        )
        self._handle = kernel32.OpenProcess(access, False, pid)

    def exited(self, wait_s: float) -> bool:
        if not self._handle:
            return True  # could not be opened: it had already exited
        return self._kernel32.WaitForSingleObject(self._handle, int(wait_s * 1000)) == 0

    def terminate(self) -> None:
        if self._handle:
            self._kernel32.TerminateProcess(self._handle, 1)

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class _WorkerProcess:
    """One worker subprocess with background readers for stdout and stderr.

    On Windows a virtual environment's python.exe is a launcher that runs the real
    interpreter as its own child process. The launcher kills that child when it is
    terminated (verified on the demonstration laptop), and the worker reports its
    interpreter PID when ready so that kill() can confirm it is gone and terminate it
    through a handle opened at that time if it is not.
    """

    def __init__(self, process: subprocess.Popen) -> None:
        self.process = process
        self.pid = process.pid
        self.interpreter_pid: int | None = None
        self._interpreter: _WindowsProcessHandle | None = None
        # close() may stop a loading worker from another thread while the loading
        # thread also stops it; this lock makes kill() and attach_interpreter() safe.
        self._kill_lock = threading.Lock()
        self._killed = False
        self._lines: queue.Queue[bytes | None] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._readers = [
            threading.Thread(target=self._pump_stdout, daemon=True, name=f"worker-{self.pid}-out"),
            threading.Thread(target=self._pump_stderr, daemon=True, name=f"worker-{self.pid}-err"),
        ]
        for reader in self._readers:
            reader.start()

    def _pump_stdout(self) -> None:
        try:
            for raw in iter(self.process.stdout.readline, b""):
                self._lines.put(raw)
        except (OSError, ValueError):
            pass
        finally:
            self._lines.put(None)

    def _pump_stderr(self) -> None:
        try:
            for raw in iter(self.process.stderr.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._stderr_tail.append(line)
                    logger.debug("model worker %s: %s", self.pid, line)
        except (OSError, ValueError):
            pass

    def alive(self) -> bool:
        return self.process.poll() is None

    def attach_interpreter(self, pid: int) -> None:
        """Remember the PID the worker reported for itself (see the class docstring)."""
        with self._kill_lock:
            self.interpreter_pid = pid
            if self._killed:  # stopped already; its launcher took the interpreter with it
                return
            if os.name == "nt" and pid != self.pid and self._interpreter is None:
                self._interpreter = _WindowsProcessHandle(pid)

    def stderr_tail(self) -> list[str]:
        return list(self._stderr_tail)

    def send(self, message: dict, deadline: float) -> None:
        """Write one line; bounded by the deadline even if the worker stops reading."""
        try:
            data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        except UnicodeEncodeError as exc:  # e.g. lone surrogates in submitted text
            raise _UnencodableRequest(str(exc)) from None
        failure: list[BaseException] = []

        def write() -> None:
            try:
                self.process.stdin.write(data)
                self.process.stdin.flush()
            except (OSError, ValueError) as exc:
                failure.append(exc)

        writer = threading.Thread(target=write, daemon=True, name=f"worker-{self.pid}-in")
        writer.start()
        writer.join(max(0.0, deadline - time.monotonic()))
        if writer.is_alive():
            raise _Timeout()
        if failure:
            raise _WorkerGone(f"could not write to the worker: {failure[0]}")

    def receive(self, deadline: float) -> dict:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _Timeout()
        try:
            raw = self._lines.get(timeout=remaining)
        except queue.Empty:
            raise _Timeout() from None
        if raw is None:
            raise _WorkerGone("the worker closed its output")
        try:
            message = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise _ProtocolError(
                f"the worker wrote a line that is not JSON: {raw[:80]!r}"
            ) from None
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            raise _ProtocolError("the worker wrote JSON that is not a typed message object")
        return message

    def exit_code(self, wait_s: float = 2.0) -> int | None:
        try:
            return self.process.wait(timeout=wait_s)
        except subprocess.TimeoutExpired:
            return None

    def drain_stderr(self, wait_s: float = 1.0) -> None:
        """After the process exited, let the stderr reader collect the last lines."""
        if self.process.poll() is not None:
            self._readers[1].join(timeout=wait_s)

    def kill(self) -> None:
        """Terminate this worker process only (by its own handle), then release pipes."""
        with self._kill_lock:
            self._killed = True
            self._kill_locked()

    def _kill_locked(self) -> None:
        if self.process.poll() is None:
            try:
                self.process.kill()
            except OSError:
                pass
        try:
            self.process.wait(timeout=KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            logger.error("model worker %s did not exit after kill", self.pid)
        interpreter = self._interpreter
        if interpreter is not None:
            if not interpreter.exited(INTERPRETER_EXIT_WAIT_S):
                logger.error(
                    "model worker interpreter %s outlived its launcher %s; terminating it",
                    interpreter.pid,
                    self.pid,
                )
                interpreter.terminate()
                if not interpreter.exited(KILL_WAIT_S):
                    logger.error("model worker interpreter %s did not exit", interpreter.pid)
            interpreter.close()
            self._interpreter = None
        self._close_pipes()

    def shutdown(self) -> None:
        if self.process.poll() is None:
            try:
                self.send({"type": "shutdown"}, time.monotonic() + SHUTDOWN_GRACE_S)
                self.process.wait(timeout=SHUTDOWN_GRACE_S)
            except (_Timeout, _WorkerGone, subprocess.TimeoutExpired):
                pass
        self.kill()

    def _close_pipes(self) -> None:
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except (OSError, ValueError):
                pass
        for reader in self._readers:
            reader.join(timeout=2.0)


class LocalProvider:
    """Provider backed by a pinned local model in a worker subprocess."""

    def __init__(
        self,
        settings: LocalModelSettings,
        *,
        worker_script: str | os.PathLike[str] | None = None,
    ) -> None:
        self._settings = settings
        self._worker_script = Path(worker_script) if worker_script is not None else WORKER_SCRIPT
        self._call_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._worker: _WorkerProcess | None = None
        self._loading: _WorkerProcess | None = None  # a worker that has not reported ready
        self._ready: dict | None = None
        self._last_error: str | None = None
        self._closed = False
        self._starts = 0
        self._redactions = self._build_redactions()

    @classmethod
    def from_config(cls, path: str | os.PathLike[str]) -> LocalProvider:
        """Create a provider from a JSON config file (configs/model.local.json)."""
        return cls(LocalModelSettings.from_file(path))

    @property
    def mode(self) -> ProviderMode:
        return ProviderMode.LOCAL_MODEL

    @property
    def settings(self) -> LocalModelSettings:
        return self._settings

    @property
    def worker_pid(self) -> int | None:
        """PID of the running worker's interpreter (as it reported itself), or None."""
        with self._state_lock:
            worker = self._worker
        if worker is None or not worker.alive():
            return None
        return worker.interpreter_pid or worker.pid

    @property
    def worker_starts(self) -> int:
        """How many workers finished loading since this provider was created."""
        return self._starts

    def info(self) -> ProviderInfo:
        with self._state_lock:
            worker, ready = self._worker, self._ready
            last_error, closed = self._last_error, self._closed
        loaded = worker is not None and ready is not None and worker.alive()
        if closed:
            detail = "Provider closed."
        elif loaded:
            detail = (
                f"Model loaded in {ready['load_s']:.1f} s on {ready['device']} "
                f"({ready['dtype']}); revision verified: {ready['revision_verified']}."
            )
            if ready.get("adapter_sha256"):
                detail += (
                    f" Adapter weights sha256 {ready['adapter_sha256']}, adapter config "
                    f"sha256 {ready.get('adapter_config_sha256')}."
                )
        elif last_error:
            detail = f"Model not loaded: {last_error}"
        else:
            detail = "Worker not started; the model loads on the first request."
        settings = self._settings
        return ProviderInfo(
            provider_mode=ProviderMode.LOCAL_MODEL,
            model_id=settings.model_id,
            model_revision=settings.model_revision,
            adapter_id=settings.adapter_id,
            adapter_sha256=(ready or {}).get("adapter_sha256") or settings.adapter_sha256,
            device=ready["device"] if loaded else settings.device,
            ready=loaded,
            detail=detail,
        )

    def warm_up(self) -> ProviderInfo:
        """Start the worker and load the model now instead of on the first request."""
        with self._call_lock:
            if not self._closed:
                self._ensure_worker()
        return self.info()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        timeout_s = request.config.timeout_s
        if not self._call_lock.acquire(timeout=timeout_s):
            return self._failed(
                ProviderErrorCode.BUSY,
                f"Another generation was still running after {timeout_s:.1f} s.",
                started,
            )
        try:
            return self._generate_locked(request, started)
        finally:
            self._call_lock.release()

    def close(self) -> None:
        """Stop the worker, including one that is still loading. Idempotent.

        Later calls return unavailable. A worker that is still loading the model is
        killed at once (the loading call then fails); a ready worker gets a graceful
        shutdown unless a generation is still running, in which case it is killed.
        """
        got_lock = self._call_lock.acquire(timeout=CLOSE_LOCK_WAIT_S)
        try:
            with self._state_lock:
                self._closed = True
                worker, self._worker, self._ready = self._worker, None, None
                loading, self._loading = self._loading, None
            if loading is not None:
                loading.kill()
            if worker is not None:
                if got_lock:
                    worker.shutdown()
                else:  # a call is still running: stop it now rather than wait for it
                    worker.kill()
        finally:
            if got_lock:
                self._call_lock.release()

    def __enter__(self) -> LocalProvider:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- internals (called with the call lock held) ------------------------------------

    def _generate_locked(self, request: GenerationRequest, started: float) -> GenerationResult:
        if self._closed:
            return self._failed(ProviderErrorCode.UNAVAILABLE, "The provider is closed.", started)
        if request.use_adapter and self._settings.adapter_dir is None:
            return self._failed(
                ProviderErrorCode.UNAVAILABLE,
                "use_adapter=true but no LoRA adapter is configured (adapter_dir is null); "
                "the base model is never used as a fallback.",
                started,
            )
        starts_before = self._starts
        worker, load_error = self._ensure_worker()
        if worker is None:
            return self._failed(ProviderErrorCode.MODEL_LOAD_ERROR, load_error, started)
        warnings = []
        if self._starts != starts_before:
            load_s = self._ready["load_s"]
            warnings.append(
                f"The model worker started during this call (model load {load_s:.1f} s)."
            )
        config = request.config
        request_id = uuid.uuid4().hex
        message = {
            "type": "generate",
            "id": request_id,
            "messages": [m.model_dump() for m in request.messages],
            "max_new_tokens": config.max_new_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "seed": config.seed,
            "max_input_tokens": config.max_input_tokens,
            "use_adapter": request.use_adapter,
        }
        deadline = time.monotonic() + config.timeout_s
        try:
            worker.send(message, deadline)
            reply = worker.receive(deadline)
            return self._result_from_reply(reply, request, request_id, started, warnings)
        except _UnencodableRequest:
            return self._failed(
                ProviderErrorCode.GENERATION_ERROR,
                "The request contains text that cannot be encoded as UTF-8.",
                started,
            )
        except _Timeout:
            self._discard_worker(f"generation exceeded timeout_s={config.timeout_s}")
            return self._failed(
                ProviderErrorCode.TIMEOUT,
                f"Generation exceeded {config.timeout_s:.1f} s; the model worker was stopped "
                "and will restart on the next call.",
                started,
            )
        except _WorkerGone:
            code = worker.exit_code()
            tail = self._tail(worker)
            self._discard_worker("worker exited during generation")
            return self._failed(
                ProviderErrorCode.GENERATION_ERROR,
                f"The model worker exited unexpectedly (exit code {code}).{tail}",
                started,
            )
        except _ProtocolError as exc:
            self._discard_worker(f"protocol error: {exc}")
            return self._failed(
                ProviderErrorCode.GENERATION_ERROR,
                f"Model worker protocol error: {exc} The worker was stopped and will restart "
                "on the next call.",
                started,
            )

    def _result_from_reply(
        self,
        reply: dict,
        request: GenerationRequest,
        request_id: str,
        started: float,
        warnings: list[str],
    ) -> GenerationResult:
        if reply.get("id") != request_id:
            raise _ProtocolError("the reply does not belong to this request.")
        if reply["type"] == "error":
            raw_code = reply.get("code")
            code = _WORKER_ERRORS.get(raw_code) if isinstance(raw_code, str) else None
            if code is None or not isinstance(reply.get("message"), str):
                raise _ProtocolError("the worker sent an error without a known code and message.")
            if reply.get("fatal") is True:  # e.g. a CUDA error that leaves the device unusable
                self._discard_worker("the worker reported a fatal device error")
                return self._failed(
                    code,
                    f"{reply['message']} The model worker was stopped and will restart on the "
                    "next call.",
                    started,
                )
            return self._failed(code, reply["message"], started)
        if reply["type"] != "result":
            raise _ProtocolError(f"unexpected message type {reply['type']!r}.")
        text = reply.get("text")
        prompt_tokens = reply.get("prompt_tokens")
        completion_tokens = reply.get("completion_tokens")
        finish_reason = reply.get("finish_reason")
        if (
            not isinstance(text, str)
            or not _is_count(prompt_tokens)
            or not _is_count(completion_tokens)
            or finish_reason not in ("stop", "length")
            or reply.get("use_adapter") is not request.use_adapter
        ):
            raise _ProtocolError("the result fields are missing or invalid.")
        if self._ready is not None and not self._ready.get("revision_verified"):
            warnings.append(
                "The model files' revision could not be verified from download metadata."
            )
        return GenerationResult(
            text=text,
            provider_mode=ProviderMode.LOCAL_MODEL,
            model=self._model_reference(request.use_adapter),
            elapsed_s=time.perf_counter() - started,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason=finish_reason,
            warnings=warnings,
        )

    def _model_reference(self, use_adapter: bool) -> ModelReference:
        ready = self._ready or {}
        return ModelReference(
            model_id=ready["model_id"],
            model_revision=ready["model_revision"],
            adapter_id=ready.get("adapter_id"),
            adapter_sha256=ready.get("adapter_sha256"),
            use_adapter=use_adapter,
        )

    def _ensure_worker(self) -> tuple[_WorkerProcess | None, str]:
        """Return a loaded worker, starting one if needed, or (None, error message)."""
        worker = self._worker
        if worker is not None and worker.alive() and self._ready is not None:
            return worker, ""
        if worker is not None:
            self._discard_worker("worker was not running")
        problem = self._precheck()
        if problem:
            return self._load_failed(None, problem)
        settings = self._settings
        # -I: isolated mode (no user site, no PYTHON* variables, script dir not on sys.path);
        # -X utf8: UTF-8 mode for stdio and files; -u: unbuffered stderr for live logs.
        command = [str(settings.python), "-I", "-X", "utf8", "-u", str(self._worker_script)]
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONIOENCODING": "utf-8",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            return self._load_failed(None, f"could not start the model worker: {exc}")
        worker = _WorkerProcess(process)
        logger.info("started model worker pid %s", worker.pid)
        with self._state_lock:  # close() can now stop this worker while it loads
            closed = self._closed
            if not closed:
                self._loading = worker
        if closed:
            worker.kill()
            return None, "The provider is closed."
        try:
            return self._load(worker)
        finally:
            with self._state_lock:
                if self._loading is worker:
                    self._loading = None

    def _load(self, worker: _WorkerProcess) -> tuple[_WorkerProcess | None, str]:
        """Send the load message and wait for the worker to report ready."""
        settings = self._settings
        load = {
            "type": "load",
            "protocol": PROTOCOL_VERSION,
            "model_dir": str(settings.model_dir),
            "model_id": settings.model_id,
            "model_revision": settings.model_revision,
            "adapter_dir": None if settings.adapter_dir is None else str(settings.adapter_dir),
            "adapter_id": settings.adapter_id,
            "adapter_sha256": settings.adapter_sha256,
            "adapter_config_sha256": settings.adapter_config_sha256,
            "device": settings.device,
            "dtype": settings.dtype,
        }
        deadline = time.monotonic() + settings.load_timeout_s
        try:
            worker.send(load, deadline)
            reply = worker.receive(deadline)
            if reply["type"] == "starting":
                pid = reply.get("pid")
                if reply.get("protocol") != PROTOCOL_VERSION or not _is_count(pid) or pid == 0:
                    raise _ProtocolError("the starting message has no valid protocol and pid")
                worker.attach_interpreter(pid)
                reply = worker.receive(deadline)
            elif reply["type"] != "load_error":
                raise _ProtocolError(f"expected a starting message, got {reply['type']!r}")
        except _Timeout:
            return self._load_failed(
                worker, f"the model did not finish loading within {settings.load_timeout_s:.0f} s"
            )
        except _WorkerGone:
            code = worker.exit_code()
            return self._load_failed(
                worker,
                f"the model worker exited while loading (exit code {code}).{self._tail(worker)}",
            )
        except _ProtocolError as exc:
            return self._load_failed(worker, f"model worker protocol error while loading: {exc}")
        if reply["type"] == "load_error":
            return self._load_failed(worker, str(reply.get("message", "unknown load error")))
        problem = self._check_ready(reply)
        if problem:
            return self._load_failed(worker, problem)
        with self._state_lock:
            closed = self._closed
            if not closed:
                self._worker, self._ready, self._last_error = worker, reply, None
                self._loading = None
        if closed:  # close() ran while this worker was loading
            worker.kill()
            return None, "The provider is closed."
        self._starts += 1
        logger.info(
            "model worker ready: launcher pid %s, interpreter pid %s, load %.1f s",
            worker.pid,
            worker.interpreter_pid,
            reply["load_s"],
        )
        return worker, ""

    def _precheck(self) -> str:
        settings = self._settings
        if not settings.python.is_file():
            return "the training-environment interpreter (python) was not found"
        if not self._worker_script.is_file():
            return "the model worker script was not found"
        if not settings.model_dir.is_dir():
            return "model_dir does not exist or is not a directory"
        if settings.adapter_dir is not None and not settings.adapter_dir.is_dir():
            return "adapter_dir does not exist or is not a directory"
        return ""

    def _check_ready(self, reply: dict) -> str:
        settings = self._settings
        if reply.get("type") != "ready" or reply.get("protocol") != PROTOCOL_VERSION:
            return "the model worker sent an unexpected message while loading"
        if (
            reply.get("model_id") != settings.model_id
            or reply.get("model_revision") != settings.model_revision
            or reply.get("adapter_id") != settings.adapter_id
        ):
            return "the model worker loaded a different model identity than configured"
        sha = reply.get("adapter_sha256")
        if settings.adapter_dir is None:
            if sha is not None:
                return "the model worker reported an adapter although none is configured"
        elif not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            return "the model worker did not report the adapter checksum"
        elif settings.adapter_sha256 is not None and sha != settings.adapter_sha256:
            return "the loaded adapter checksum does not match adapter_sha256"
        config_sha = reply.get("adapter_config_sha256")
        if settings.adapter_dir is None:
            if config_sha is not None:
                return "the model worker reported an adapter config although none is configured"
        elif not isinstance(config_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", config_sha):
            return "the model worker did not report the adapter config checksum"
        elif (
            settings.adapter_config_sha256 is not None
            and config_sha != settings.adapter_config_sha256
        ):
            return "the loaded adapter config checksum does not match adapter_config_sha256"
        if (
            not isinstance(reply.get("load_s"), (int, float))
            or isinstance(reply.get("load_s"), bool)
            or not isinstance(reply.get("device"), str)
            or reply.get("dtype") != settings.dtype
            or not isinstance(reply.get("revision_verified"), bool)
        ):
            return "the model worker's ready message is incomplete or inconsistent"
        return ""

    def _load_failed(self, worker: _WorkerProcess | None, message: str) -> tuple[None, str]:
        if worker is not None:
            worker.kill()
        if self._closed:  # close() stopped the load
            return None, "The provider is closed."
        message = self._redact(message)
        with self._state_lock:
            self._last_error = message
        logger.warning("model load failed: %s", message)
        return None, message

    def _discard_worker(self, reason: str) -> None:
        with self._state_lock:
            worker, self._worker, self._ready = self._worker, None, None
        if worker is not None:
            logger.warning("stopping model worker %s: %s", worker.pid, reason)
            worker.kill()

    def _tail(self, worker: _WorkerProcess) -> str:
        worker.drain_stderr()
        lines = worker.stderr_tail()
        return f" Last worker log line: {lines[-1][:300]}" if lines else ""

    def _failed(self, code: ProviderErrorCode, message: str, started: float) -> GenerationResult:
        text = self._redact(message)
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[: MAX_MESSAGE_CHARS - 3] + "..."
        return failed_result(self.mode, code, text, time.perf_counter() - started)

    def _build_redactions(self) -> list[tuple[re.Pattern[str], str]]:
        """Host paths never reach run records or the UI; they are replaced by key names."""
        settings = self._settings
        candidates = [
            (settings.adapter_dir, "<adapter_dir>"),
            (settings.model_dir, "<model_dir>"),
            (settings.python, "<python>"),
            (self._worker_script.parent, "<worker_dir>"),
        ]
        try:
            candidates.append((Path.home(), "~"))
        except RuntimeError:  # no home directory can be determined
            pass
        patterns = []
        for path, label in candidates:
            if path is None:
                continue
            for variant in {str(path), str(path).replace("\\", "/"), path.as_posix()}:
                if len(variant) > 3:
                    flags = re.IGNORECASE if os.name == "nt" else 0
                    patterns.append((len(variant), re.compile(re.escape(variant), flags), label))
        patterns.sort(key=lambda item: -item[0])
        return [(pattern, label) for _, pattern, label in patterns]

    def _redact(self, message: str) -> str:
        for pattern, label in self._redactions:
            message = pattern.sub(label, message)
        return message


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

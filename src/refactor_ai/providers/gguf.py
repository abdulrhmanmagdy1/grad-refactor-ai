"""Providers for the project review mode: a GGUF model on llama.cpp and a one-model GPU pool.

GgufProvider is LocalProvider (same worker protocol, process handling, timeouts, typed
errors and host-path redaction) with gguf_worker.py as the worker script and four more
settings: gguf_file, gguf_sha256, context_tokens and gpu_layers (see
configs/model.project.example.json). It checks that the worker reports the GGUF checksum,
and that the checksum matches gguf_sha256 when one is configured.

The laptop's 4 GB GPU holds one model at a time. ModelPool keeps at most one member
loaded: a PooledProvider call holds the pool for its whole duration, stopping the worker of
any other member first, so two models are never loaded together; the other member reloads
on its next call. A call that cannot get the pool within its timeout_s returns busy.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from refactor_ai.contracts import (
    GenerationRequest,
    GenerationResult,
    ProviderErrorCode,
    ProviderInfo,
    ProviderMode,
)
from refactor_ai.providers.base import failed_result
from refactor_ai.providers.local import LocalModelSettings, LocalProvider

GGUF_WORKER_SCRIPT = Path(__file__).with_name("gguf_worker.py")


class GgufModelSettings(LocalModelSettings):
    """LocalModelSettings for one GGUF file (configs/model.project.local.json)."""

    gguf_file: str = Field(pattern=r"^[^/\\]+\.gguf$")
    gguf_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    context_tokens: int = Field(default=8192, ge=256, le=131072)
    gpu_layers: int = Field(default=-1, ge=-1)
    dtype: Literal["bfloat16", "float16", "float32"] = "float16"

    @model_validator(mode="after")
    def _no_adapter(self) -> GgufModelSettings:
        if self.adapter_dir is not None:
            raise ValueError("a GGUF model is served without a LoRA adapter")
        return self


class ReleasableLocalProvider(LocalProvider):
    """LocalProvider that can free the GPU and load again on its next call."""

    @property
    def last_error(self) -> str | None:
        """The last load error, if the model failed to load."""
        return self._last_error

    def release(self) -> None:
        """Stop the worker but keep the provider usable. A running call finishes first."""
        with self._call_lock:
            with self._state_lock:
                worker, self._worker, self._ready = self._worker, None, None
            if worker is not None:
                worker.shutdown()


class GgufProvider(ReleasableLocalProvider):
    """A pinned GGUF model served by llama.cpp in a worker subprocess."""

    def __init__(
        self,
        settings: GgufModelSettings,
        *,
        worker_script: str | os.PathLike[str] | None = None,
    ) -> None:
        super().__init__(settings, worker_script=worker_script or GGUF_WORKER_SCRIPT)

    @classmethod
    def from_config(cls, path: str | os.PathLike[str]) -> GgufProvider:
        return cls(GgufModelSettings.from_file(path))

    def info(self) -> ProviderInfo:
        info = super().info()
        ready = self._ready
        if info.ready and ready and ready.get("gguf_sha256"):
            return info.model_copy(
                update={"detail": f"{info.detail} GGUF sha256 {ready['gguf_sha256']}."}
            )
        return info

    def _load(self, worker):
        settings = self._settings
        extra = {
            "gguf_file": settings.gguf_file,
            "gguf_sha256": settings.gguf_sha256,
            "context_tokens": settings.context_tokens,
            "gpu_layers": settings.gpu_layers,
        }
        send = worker.send

        def send_with_gguf_fields(message: dict, deadline: float) -> None:
            if message.get("type") == "load":
                message = {**message, **extra}
            send(message, deadline)

        worker.send = send_with_gguf_fields
        return super()._load(worker)

    def _precheck(self) -> str:
        problem = super()._precheck()
        if problem:
            return problem
        if not (self._settings.model_dir / self._settings.gguf_file).is_file():
            return "gguf_file was not found in model_dir"
        return ""

    def _check_ready(self, reply: dict) -> str:
        problem = super()._check_ready(reply)
        if problem:
            return problem
        sha = reply.get("gguf_sha256")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            return "the model worker did not report the GGUF checksum"
        if self._settings.gguf_sha256 is not None and sha != self._settings.gguf_sha256:
            return "the loaded GGUF checksum does not match gguf_sha256"
        return ""


class ModelPool:
    """At most one member keeps its model loaded; using one releases the others."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._members: list[ReleasableLocalProvider] = []
        self._active: ReleasableLocalProvider | None = None

    def add(self, provider: ReleasableLocalProvider) -> None:
        with self._lock:
            if provider not in self._members:
                self._members.append(provider)

    @property
    def active(self) -> ReleasableLocalProvider | None:
        return self._active

    def acquire(self, provider: ReleasableLocalProvider, timeout_s: float) -> bool:
        """Hold the pool with `provider` as the only loaded member; False on timeout."""
        if not self._lock.acquire(timeout=timeout_s):
            return False
        if self._active is not provider:
            for member in self._members:
                if member is not provider:
                    member.release()
            self._active = provider
        return True

    def release(self) -> None:
        self._lock.release()


class PooledProvider:
    """A Provider whose calls hold the pool, so its model is the only one loaded."""

    def __init__(self, inner: ReleasableLocalProvider, pool: ModelPool) -> None:
        self.inner = inner
        self.pool = pool
        pool.add(inner)

    @property
    def mode(self) -> ProviderMode:
        return self.inner.mode

    def info(self) -> ProviderInfo:
        """The inner provider's information; a model stopped because the other member
        holds the GPU is reported as paused, not as failed."""
        info = self.inner.info()
        other_active = self.pool.active is not None and self.pool.active is not self.inner
        if not info.ready and other_active and not self.inner.last_error:
            return info.model_copy(
                update={
                    "detail": "Paused: the other model is using the GPU; this model loads "
                    "again on its next call."
                }
            )
        return info

    def warm_up(self) -> ProviderInfo:
        if not self.pool.acquire(self.inner, timeout_s=self.inner.settings.load_timeout_s):
            return self.inner.info()
        try:
            return self.inner.warm_up()
        finally:
            self.pool.release()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        timeout_s = request.config.timeout_s
        if not self.pool.acquire(self.inner, timeout_s=timeout_s):
            return failed_result(
                self.mode,
                ProviderErrorCode.BUSY,
                f"Another model was still in use after {timeout_s:.1f} s.",
                time.perf_counter() - started,
            )
        try:
            return self.inner.generate(request)
        finally:
            self.pool.release()

    def close(self) -> None:
        self.inner.close()

    def __getattr__(self, name: str):
        """Everything else (worker_pid, settings, ...) is the inner provider's."""
        return getattr(self.inner, name)

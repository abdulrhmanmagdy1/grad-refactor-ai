"""Helpers shared by the training-environment scripts (benchmark, training, adapter check)."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import shutil
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "src", ROOT / "training"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

PACKAGES = (
    "torch",
    "transformers",
    "peft",
    "accelerate",
    "datasets",
    "huggingface-hub",
    "safetensors",
    "tokenizers",
)


def load_worker_module():
    """Import providers/model_worker.py by path; the package __init__ needs pydantic."""
    name = "refactor_ai_model_worker"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "src" / "refactor_ai" / "providers" / "model_worker.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, str | None]:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def git_state() -> dict:
    """HEAD commit plus whether the working tree differs from it (uncommitted changes)."""

    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
            )
        except (OSError, subprocess.SubprocessError):  # missing git, or a hung one (timeout)
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    status = run("status", "--porcelain")
    return {"head": run("rev-parse", "HEAD"), "dirty": None if status is None else bool(status)}


def nvidia_smi(query: str) -> str | None:
    """One nvidia-smi --query-gpu value line, or None when unavailable."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        # OSError: no process could be started (e.g. memory pressure);
        # SubprocessError: nvidia-smi hung past the timeout (e.g. a wedged driver).
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def gpu_used_mib() -> int | None:
    """GPU memory in use by all processes (the desktop included), from nvidia-smi."""
    value = nvidia_smi("memory.used")
    try:
        return int(value.splitlines()[0]) if value else None
    except ValueError:
        return None


class GpuSampler:
    """Polls total GPU memory in use (all processes) to catch the peak during a phase."""

    def __init__(self, interval_s: float = 0.5) -> None:
        self.interval_s = interval_s
        self.peak: int | None = None
        self.samples = 0
        self.failures = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                used = gpu_used_mib()
            except Exception:  # a failed sample must not end the sampling thread
                self.failures += 1
                used = None
            if used is not None:
                self.samples += 1
                self.peak = used if self.peak is None else max(self.peak, used)
            self._stop.wait(self.interval_s)

    def __enter__(self) -> GpuSampler:
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


def free_disk_mb(path: Path = ROOT) -> int:
    return shutil.disk_usage(path).free // 2**20


def require_free_disk(min_mb: int, needed_mb: int = 0, path: Path = ROOT) -> int:
    """Stop with a clear blocker when writing needed_mb would leave less than min_mb free."""
    free = free_disk_mb(path)
    if free - needed_mb < min_mb:
        raise SystemExit(
            f"BLOCKER: {free} MB free; writing about {needed_mb} MB would leave less than "
            f"the {min_mb} MB floor"
        )
    return free

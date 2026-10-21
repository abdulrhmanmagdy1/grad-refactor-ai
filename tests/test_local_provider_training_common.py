"""training/common.py helpers that must degrade to None instead of crashing a run.

The module is standard-library only, so core CI imports it by path (it adds src/ and
training/ to sys.path, which these tests undo).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def common(monkeypatch):
    saved = list(sys.path)
    spec = importlib.util.spec_from_file_location(
        "training_common_under_test", ROOT / "training" / "common.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path[:] = saved
    return module


def hung(*args, **kwargs):
    """subprocess.run replacement that behaves like a command that never returns."""
    raise subprocess.TimeoutExpired(cmd=args[0] if args else "cmd", timeout=kwargs.get("timeout"))


def test_nvidia_smi_returns_none_when_it_hangs(common, monkeypatch):
    monkeypatch.setattr(common.shutil, "which", lambda name: "nvidia-smi")
    monkeypatch.setattr(common.subprocess, "run", hung)
    assert common.nvidia_smi("memory.used") is None
    assert common.gpu_used_mib() is None


def test_nvidia_smi_returns_none_when_it_cannot_start(common, monkeypatch):
    def cannot_start(*args, **kwargs):
        raise OSError(1455, "The paging file is too small for this operation to complete")

    monkeypatch.setattr(common.shutil, "which", lambda name: "nvidia-smi")
    monkeypatch.setattr(common.subprocess, "run", cannot_start)
    assert common.nvidia_smi("memory.used") is None


def test_git_state_returns_unknown_when_git_hangs(common, monkeypatch):
    monkeypatch.setattr(common.subprocess, "run", hung)
    assert common.git_state() == {"head": None, "dirty": None}


def test_gpu_sampler_survives_failing_samples(common, monkeypatch):
    calls = {"n": 0}

    def flaky() -> int:
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise RuntimeError("sample failed")
        return 1000 + calls["n"]

    monkeypatch.setattr(common, "gpu_used_mib", flaky)
    sampler = common.GpuSampler(interval_s=0.01)
    with sampler:
        deadline = time.monotonic() + 5
        while (sampler.samples < 3 or sampler.failures < 3) and time.monotonic() < deadline:
            time.sleep(0.01)
        alive = sampler._thread.is_alive()
    assert alive, "a failed sample ended the sampling thread"
    assert sampler.samples >= 3 and sampler.failures >= 3
    assert sampler.peak is not None and sampler.peak > 1000

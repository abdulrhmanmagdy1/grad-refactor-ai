"""Best-effort resource measurements; each returns (value, None) or (None, reason).

worker peak RSS: the peak working set (Windows) or VmHWM (Linux) of the model worker
process since it started, read from the operating system without third-party packages.
It is cumulative, not per call. GPU memory: the device's used memory reported by
nvidia-smi right after a case, which shows the resident model rather than the per-call
peak. Neither is invented when unavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def process_peak_rss_mb(pid: int | None) -> tuple[float | None, str | None]:
    if pid is None:
        return None, "the provider exposes no worker process id"
    try:
        if sys.platform == "win32":
            return _windows_peak_rss_mb(pid), None
        status = Path(f"/proc/{pid}/status")
        if status.exists():
            for line in status.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmHWM:"):
                    return round(int(line.split()[1]) / 1024, 1), None
        return None, f"peak RSS is not available on {sys.platform}"
    except OSError as exc:
        return None, f"peak RSS could not be read: {exc}"


def _windows_peak_rss_mb(pid: int) -> float:
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    query_limited, vm_read = 0x1000, 0x0010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(query_limited | vm_read, False, pid)
    if not handle:
        raise OSError(f"OpenProcess failed with error {ctypes.get_last_error()}")
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise OSError(f"GetProcessMemoryInfo failed with error {ctypes.get_last_error()}")
        return round(counters.PeakWorkingSetSize / (1024 * 1024), 1)
    finally:
        kernel32.CloseHandle(handle)


def gpu_memory_used_mb() -> tuple[float | None, str | None]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None, "nvidia-smi is not available"
    try:
        completed = subprocess.run(
            [executable, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={**os.environ},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"nvidia-smi failed: {exc}"
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or not lines:
        return None, f"nvidia-smi returned {completed.returncode}"
    try:
        return float(lines[0]), None
    except ValueError:
        return None, f"unexpected nvidia-smi output: {lines[0][:60]}"

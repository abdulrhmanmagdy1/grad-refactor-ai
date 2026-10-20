"""Windows Job Object limits for the reference runner's test process (ctypes, kernel32).

Used only by the runner process (never by the test process, which refuses ctypes). The
test process is created suspended, assigned to a job that limits committed memory, user
CPU time and the number of active processes (one: no child processes), restricts desktop
interaction and kills every member when the job closes. Only then are its threads
resumed. No administrator rights are needed.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

if sys.platform != "win32":  # pragma: no cover - imported only on Windows
    raise ImportError("refactor_ai.verification._winjob is Windows-only")

CREATE_SUSPENDED = 0x00000004
DETACHED_PROCESS = 0x00000008
STATUS_QUOTA_EXCEEDED = 0xC0000044

_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_THREAD_SUSPEND_RESUME = 0x0002
_TH32CS_SNAPTHREAD = 0x00000004
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_JOB_BASIC_ACCOUNTING = 1
_JOB_BASIC_UI_RESTRICTIONS = 4
_JOB_EXTENDED_LIMITS = 9

_LIMIT_PROCESS_TIME = 0x00000002
_LIMIT_ACTIVE_PROCESS = 0x00000008
_LIMIT_PROCESS_MEMORY = 0x00000100
_LIMIT_JOB_MEMORY = 0x00000200
_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
# Handles, clipboard, system parameters, display settings, global atoms, desktop, exit.
_UI_RESTRICT_ALL = 0x000000FF


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class _UiRestrictions(ctypes.Structure):
    _fields_ = [("UIRestrictionsClass", wintypes.DWORD)]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _declare(name: str, restype, *argtypes):
    function = getattr(_kernel32, name)
    function.restype = restype
    function.argtypes = list(argtypes)
    return function


_CreateJobObjectW = _declare("CreateJobObjectW", wintypes.HANDLE, ctypes.c_void_p, wintypes.LPCWSTR)
_SetInformationJobObject = _declare(
    "SetInformationJobObject",
    wintypes.BOOL,
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
)
_QueryInformationJobObject = _declare(
    "QueryInformationJobObject",
    wintypes.BOOL,
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
)
_AssignProcessToJobObject = _declare(
    "AssignProcessToJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE
)
_IsProcessInJob = _declare(
    "IsProcessInJob",
    wintypes.BOOL,
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.BOOL),
)
_TerminateJobObject = _declare("TerminateJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
_CloseHandle = _declare("CloseHandle", wintypes.BOOL, wintypes.HANDLE)
_OpenProcess = _declare(
    "OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
)
_OpenThread = _declare("OpenThread", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_ResumeThread = _declare("ResumeThread", wintypes.DWORD, wintypes.HANDLE)
_CreateToolhelp32Snapshot = _declare(
    "CreateToolhelp32Snapshot", wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD
)
_Thread32First = _declare(
    "Thread32First", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)
)
_Thread32Next = _declare(
    "Thread32Next", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)
)


def _error(what: str) -> OSError:
    code = ctypes.get_last_error()
    error = ctypes.WinError(code)
    return OSError(error.errno, f"{what} failed: {error.strerror}", None, code)


class JobObject:
    """A kill-on-close job with memory, CPU-time and active-process limits."""

    def __init__(self, *, memory_bytes: int, cpu_seconds: float, active_processes: int = 1):
        handle = _CreateJobObjectW(None, None)
        if not handle:
            raise _error("CreateJobObjectW")
        self._handle: int | None = handle
        try:
            limits = _ExtendedLimits()
            basic = limits.BasicLimitInformation
            basic.LimitFlags = (
                _LIMIT_PROCESS_TIME
                | _LIMIT_ACTIVE_PROCESS
                | _LIMIT_PROCESS_MEMORY
                | _LIMIT_JOB_MEMORY
                | _LIMIT_DIE_ON_UNHANDLED_EXCEPTION
                | _LIMIT_KILL_ON_JOB_CLOSE
            )
            basic.ActiveProcessLimit = active_processes
            basic.PerProcessUserTimeLimit = int(cpu_seconds * 10_000_000)  # 100 ns units
            limits.ProcessMemoryLimit = memory_bytes
            limits.JobMemoryLimit = memory_bytes
            if not _SetInformationJobObject(
                handle, _JOB_EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise _error("SetInformationJobObject(limits)")
            restrictions = _UiRestrictions(_UI_RESTRICT_ALL)
            if not _SetInformationJobObject(
                handle,
                _JOB_BASIC_UI_RESTRICTIONS,
                ctypes.byref(restrictions),
                ctypes.sizeof(restrictions),
            ):
                raise _error("SetInformationJobObject(UI restrictions)")
        except BaseException:
            self.close()
            raise

    @property
    def handle(self) -> int:
        if self._handle is None:
            raise ValueError("The job object is closed")
        return self._handle

    def assign(self, pid: int) -> None:
        """Assign a (suspended) process and confirm that it is in this job."""
        process = _OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE | _PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        if not process:
            raise _error("OpenProcess")
        try:
            if not _AssignProcessToJobObject(self.handle, process):
                raise _error("AssignProcessToJobObject")
            member = wintypes.BOOL(False)
            if not _IsProcessInJob(process, self.handle, ctypes.byref(member)):
                raise _error("IsProcessInJob")
            if not member.value:
                raise OSError("The test process is not in the job after assignment")
        finally:
            _CloseHandle(process)

    def terminate(self, exit_code: int = 1) -> None:
        if self._handle is not None:
            _TerminateJobObject(self._handle, exit_code)

    def accounting(self) -> tuple[int, int, int]:
        """(total processes, active processes, processes terminated by a limit)."""
        info = _Accounting()
        if not _QueryInformationJobObject(
            self.handle, _JOB_BASIC_ACCOUNTING, ctypes.byref(info), ctypes.sizeof(info), None
        ):
            raise _error("QueryInformationJobObject(accounting)")
        return info.TotalProcesses, info.ActiveProcesses, info.TotalTerminatedProcesses

    def peak_process_memory(self) -> int:
        info = _ExtendedLimits()
        if not _QueryInformationJobObject(
            self.handle, _JOB_EXTENDED_LIMITS, ctypes.byref(info), ctypes.sizeof(info), None
        ):
            raise _error("QueryInformationJobObject(limits)")
        return int(info.PeakProcessMemoryUsed)

    def wait_until_empty(self, timeout_s: float) -> bool:
        """True once no process of the job is active."""
        deadline = time.monotonic() + timeout_s
        while True:
            if self.accounting()[1] == 0:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def close(self) -> None:
        """Close the job; kill-on-close terminates any remaining member."""
        if self._handle is not None:
            handle, self._handle = self._handle, None
            _CloseHandle(handle)


def resume_process(pid: int) -> int:
    """Resume every thread of a process created suspended; returns the number resumed."""
    snapshot = _CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
    if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
        raise _error("CreateToolhelp32Snapshot")
    resumed = 0
    try:
        entry = _ThreadEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = _Thread32First(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == pid:
                thread = _OpenThread(_THREAD_SUSPEND_RESUME, False, entry.th32ThreadID)
                if not thread:
                    raise _error("OpenThread")
                try:
                    if _ResumeThread(thread) == 0xFFFFFFFF:
                        raise _error("ResumeThread")
                finally:
                    _CloseHandle(thread)
                resumed += 1
            more = _Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        _CloseHandle(snapshot)
    if resumed == 0:
        raise OSError("No thread of the test process was found to resume")
    return resumed

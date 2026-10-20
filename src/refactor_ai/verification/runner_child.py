"""Isolated test process of the trusted reference runner (standard library only).

refactor_ai.verification.runner starts this file as

    <base interpreter> -I -S -B -X utf8 runner_child.py

with an empty environment (only SYSTEMROOT on Windows), a fresh temporary working
directory as its current directory and, on Windows, inside a Job Object assigned while
the process was still suspended. The first statement of main() installs an audit hook.
The trusted setup then reads one JSON payload from stdin, applies POSIX resource limits,
compiles the candidate and parses every test literal; only after that does the hook
switch to its strict phase and candidate code run.

Results are lines "<nonce> <json>" written to a private duplicate of the original stdout;
file descriptor 1 points to the null device before candidate code runs, so print() or a
write to descriptor 1 cannot reach the result channel.

This hardens execution of model-generated candidates against server-owned test cases.
It is not a sandbox for hostile code; docs/development/runner-safety.md lists the limits.
"""

import sys

PROTOCOL_VERSION = 1
NO_HOOK_FLAG = "--self-check-without-audit-hook"
MAX_DETAIL_CHARS = 400

# Root modules that code under test may not import (the event is raised only for modules
# that are not loaded yet; operations of already loaded modules are guarded by events).
BLOCKED_MODULES = frozenset(
    {
        "_asyncio",
        "_ctypes",
        "_multiprocessing",
        "_overlapped",
        "_posixsubprocess",
        "_socket",
        "_sqlite3",
        "_ssl",
        "_thread",
        "_tracemalloc",
        "_winapi",
        "asyncio",
        "bdb",
        "code",
        "codeop",
        "concurrent",
        "ctypes",
        "faulthandler",
        "fcntl",
        "ftplib",
        "gc",
        "http",
        "imaplib",
        "importlib",
        "inspect",
        "mmap",
        "msvcrt",
        "multiprocessing",
        "nntplib",
        "pdb",
        "pickle",
        "platform",
        "poplib",
        "pty",
        "resource",
        "runpy",
        "select",
        "selectors",
        "shutil",
        "signal",
        "smtplib",
        "socket",
        "socketserver",
        "sqlite3",
        "ssl",
        "subprocess",
        "telnetlib",
        "tempfile",
        "termios",
        "threading",
        "tracemalloc",
        "urllib",
        "webbrowser",
        "winreg",
        "xmlrpc",
        "zipimport",
    }
)

# Events refused in every phase: network, process creation and signalling, native code,
# the Windows API and registry, file system changes, environment changes and new hooks.
BLOCKED_EVENT_PREFIXES = (
    "_thread.start_new_thread",
    "_winapi.",
    "builtins.breakpoint",
    "builtins.input",
    "ctypes.",
    "ensurepip.",
    "fcntl.",
    "ftplib.",
    "glob.",
    "http.",
    "imaplib.",
    "mmap.",
    "msvcrt.",
    "nntplib.",
    "os.add_dll_directory",
    "os.chdir",
    "os.chflags",
    "os.chmod",
    "os.chown",
    "os.exec",
    "os.fork",
    "os.fwalk",
    "os.getxattr",
    "os.kill",
    "os.lchflags",
    "os.lchmod",
    "os.lchown",
    "os.link",
    "os.listxattr",
    "os.lockf",
    "os.mkdir",
    "os.posix_spawn",
    "os.putenv",
    "os.remove",
    "os.rename",
    "os.rmdir",
    "os.setxattr",
    "os.spawn",
    "os.startfile",
    "os.symlink",
    "os.system",
    "os.truncate",
    "os.unsetenv",
    "os.utime",
    "os.walk",
    "pathlib.",
    "pdb.",
    "poplib.",
    "pty.",
    "setopencode",
    "shutil.",
    "signal.",
    "smtplib.",
    "socket.",
    "sqlite3.",
    "subprocess.",
    "sys.addaudithook",
    "syslog.",
    "telnetlib.",
    "tempfile.",
    "urllib.",
    "webbrowser.",
    "winreg.",
)

# Allowed while the trusted harness prepares; refused once candidate code can run.
# Frame, trace and garbage-collector access would reach the harness's private state.
RUN_BLOCKED_EVENTS = frozenset(
    {
        "code.__new__",
        "function.__new__",
        "object.__getattr__",
        "resource.prlimit",
        "resource.setrlimit",
        "sys._current_exceptions",
        "sys._current_frames",
        "sys._getframe",
        "sys.setprofile",
        "sys.settrace",
    }
)
RUN_BLOCKED_PREFIXES = ("gc.",)
LISTING_EVENTS = frozenset({"os.listdir", "os.scandir"})

# Loaded during setup so that lazy imports while candidate code runs (for example an
# encoding lookup) do not need frame access, which the strict phase refuses.
PRELOADED_MODULES = (
    "cmath",
    "collections",
    "copyreg",
    "encodings.ascii",
    "encodings.idna",
    "encodings.latin_1",
    "encodings.punycode",
    "encodings.raw_unicode_escape",
    "encodings.unicode_escape",
    "encodings.utf_16",
    "encodings.utf_32",
    "enum",
    "functools",
    "keyword",
    "math",
    "operator",
    "re",
    "reprlib",
    "string",
    "stringprep",
    "types",
    "unicodedata",
    "warnings",
)

# Builtins removed from the namespace of code under test (it is also refused statically).
REMOVED_BUILTINS = (
    "__build_class__",
    "breakpoint",
    "compile",
    "copyright",
    "credits",
    "delattr",
    "eval",
    "exec",
    "exit",
    "globals",
    "help",
    "input",
    "license",
    "locals",
    "open",
    "print",
    "quit",
    "setattr",
    "vars",
)


class RunnerPolicyError(PermissionError):
    """An operation that the runner policy forbids for code under test."""


def make_audit_hook(state):
    """Audit hook enforcing the runner policy; state["phase"] is "setup" or "run"."""

    def hook(event, args):
        if event.startswith(BLOCKED_EVENT_PREFIXES):
            raise RunnerPolicyError(f"{event} is blocked by the runner policy")
        if state["phase"] == "setup":
            return
        if event == "import":
            module = args[0] if args else None
            if not isinstance(module, str) or module.partition(".")[0] in BLOCKED_MODULES:
                raise RunnerPolicyError(f"importing {module} is blocked by the runner policy")
            return
        if event == "open":
            _check_open(state, args)
            return
        if event in LISTING_EVENTS:
            _check_read_path(state, args[0] if args else None, event)
            return
        if event in RUN_BLOCKED_EVENTS or event.startswith(RUN_BLOCKED_PREFIXES):
            raise RunnerPolicyError(f"{event} is blocked by the runner policy")

    return hook


def _check_open(state, args):
    path = args[0] if args else None
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 else 0
    if isinstance(mode, str):
        writing = any(char in mode for char in "wax+")
    else:
        writing = not isinstance(flags, int) or bool(flags & state["write_flags"])
    if writing:
        raise RunnerPolicyError("writing files is blocked by the runner policy")
    _check_read_path(state, path, "open")


def _check_read_path(state, path, event):
    try:
        if path is None:
            path = "."
        if isinstance(path, bytes):
            path = state["fsdecode"](path)
        if not isinstance(path, str):
            raise TypeError("not a path")
        normalized = state["normcase"](state["abspath"](path))
    except Exception:
        raise RunnerPolicyError(f"{event} on this target is blocked by the runner policy") from None
    for root in state["roots"]:
        if normalized == root or normalized.startswith(root + state["sep"]):
            return
    raise RunnerPolicyError(f"{event} outside the allowed directories is blocked")


def _truncate(text, limit=MAX_DETAIL_CHARS):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def make_short_repr():
    import reprlib

    limits = reprlib.Repr()
    limits.maxlevel = 4
    limits.maxtuple = limits.maxlist = limits.maxarray = 8
    limits.maxdict = limits.maxset = limits.maxfrozenset = limits.maxdeque = 8
    limits.maxstring = 80
    limits.maxlong = 40
    limits.maxother = 80

    def short_repr(value):
        try:
            return limits.repr(value)
        except Exception:
            return f"<{type(value).__name__} value>"

    return short_repr


def same_value(expected, actual, depth=0):
    """Equal type and value; floats and complex numbers with relative tolerance 1e-9."""
    import cmath
    import math

    if depth > 50 or type(expected) is not type(actual):
        return False
    try:
        if isinstance(expected, float):
            return math.isclose(expected, actual, rel_tol=1e-9)
        if isinstance(expected, complex):
            return cmath.isclose(expected, actual, rel_tol=1e-9)
        if isinstance(expected, (list, tuple)):
            return len(expected) == len(actual) and all(
                same_value(e, a, depth + 1) for e, a in zip(expected, actual, strict=True)
            )
        if isinstance(expected, dict):
            if expected.keys() != actual.keys():
                return False
            actual_keys = {key: key for key in actual}
            return all(
                type(key) is type(actual_keys[key]) and same_value(value, actual[key], depth + 1)
                for key, value in expected.items()
            )
        return bool(expected == actual)
    except Exception:
        return False


def describe_exception(exc):
    try:
        message = str(exc)
    except Exception:
        message = ""
    name = type(exc).__name__
    return _truncate(f"{name}: {message}" if message else name, 200)


def render_call(function_name, args, kwargs, short_repr):
    parts = [short_repr(value) for value in args]
    parts += [f"{key}={short_repr(value)}" for key, value in kwargs.items()]
    return _truncate(f"{function_name}({', '.join(parts)})", 200)


def prepare_test(index, test, function_name, short_repr, literal_eval):
    """Parse one test's literals before candidate code runs. Returns a dict."""
    try:
        args = literal_eval(test["args"])
        kwargs = literal_eval(test["kwargs"])
        if not isinstance(args, (list, tuple)):
            raise ValueError("args must be a list or tuple literal")
        if not isinstance(kwargs, dict) or not all(isinstance(key, str) for key in kwargs):
            raise ValueError("kwargs must be a dict literal with string keys")
        kind = test["kind"]
        if kind == "return":
            if not isinstance(test.get("value"), str):
                raise ValueError("a return expectation needs a literal value")
            expected = literal_eval(test["value"])
            exception = None
        elif kind == "raise":
            exception = test.get("exception")
            if not isinstance(exception, str) or not exception.strip():
                raise ValueError("a raise expectation needs an exception type name")
            exception = exception.strip()
            expected = None
        else:
            raise ValueError(f"unknown expectation kind {kind!r}")
    except Exception as exc:
        return {
            "error": _truncate(f"Test {index} could not be prepared: {describe_exception(exc)}")
        }
    return {
        "args": tuple(args),
        "kwargs": kwargs,
        "kind": kind,
        "expected": expected,
        "exception": exception,
        "call": render_call(function_name, args, kwargs, short_repr),
        "error": None,
    }


def evaluate(prepared, func, short_repr):
    """Call the function once and compare with the expectation. Returns (kind, detail)."""
    call = prepared["call"]
    try:
        actual = func(*prepared["args"], **prepared["kwargs"])
    except BaseException as exc:  # the candidate may raise anything, including SystemExit
        # Drop the candidate's frames (and memory they hold, e.g. after MemoryError) before
        # building the report.
        exc.__traceback__ = None
        name = type(exc).__name__
        if prepared["kind"] == "raise":
            if name == prepared["exception"]:
                return "pass", None
            return "wrong_exception", (
                f"{call} raised {describe_exception(exc)}; expected {prepared['exception']}."
            )
        return "unexpected_exception", (
            f"{call} raised {describe_exception(exc)}; expected the return value "
            f"{short_repr(prepared['expected'])}."
        )
    if prepared["kind"] == "raise":
        return "missing_exception", (
            f"{call} returned {short_repr(actual)} ({type(actual).__name__}); expected "
            f"{prepared['exception']} to be raised."
        )
    if same_value(prepared["expected"], actual):
        return "pass", None
    expected = prepared["expected"]
    return "wrong_value", (
        f"{call} returned {short_repr(actual)} ({type(actual).__name__}); expected "
        f"{short_repr(expected)} ({type(expected).__name__})."
    )


class _NullWriter:
    def write(self, text):
        return len(text)

    def flush(self):
        return None


def _apply_posix_limits(limits):
    import resource

    memory = int(limits["memory_bytes"])
    cpu = max(1, int(limits["cpu_seconds"] + 0.999))
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    state = {"phase": "setup", "roots": ()}
    if NO_HOOK_FLAG not in argv:
        sys.addaudithook(make_audit_hook(state))

    import ast
    import builtins
    import json
    import os
    import types

    for name in PRELOADED_MODULES:
        __import__(name)
    # Registry-based module lookup is not needed and would touch the Windows registry.
    sys.meta_path[:] = [
        finder for finder in sys.meta_path if type(finder).__name__ != "WindowsRegistryFinder"
    ]

    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if payload.get("v") != PROTOCOL_VERSION:
        sys.stderr.write("runner child: unsupported protocol version\n")
        return 2
    nonce = str(payload["nonce"])

    # Private result channel; descriptor 1 now writes to the null device.
    result_fd = os.dup(1)
    null_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null_fd, 1)
    os.close(null_fd)
    sys.stdout = _NullWriter()
    encoder = json.JSONEncoder(ensure_ascii=True, separators=(",", ":"))

    def emit(item):
        data = memoryview(f"{nonce} {encoder.encode(item)}\n".encode("ascii"))
        while data:
            data = data[os.write(result_fd, data) :]

    limits_applied = "job"
    if os.name == "posix":
        try:
            _apply_posix_limits(payload["limits"])
        except Exception as exc:
            emit({"t": "fatal", "d": _truncate(f"resource limits failed: {exc!r}")})
            return 3
        limits_applied = "rlimit"

    workdir = os.path.normcase(os.path.abspath(os.getcwd()))
    try:
        cwd_ok = os.path.samefile(workdir, str(payload["workdir"]))
    except (KeyError, OSError, ValueError):
        cwd_ok = False
    environment = sorted(os.environ)
    roots = {os.path.normcase(os.path.abspath(entry)) for entry in sys.path if entry}
    roots.add(workdir)
    state.update(
        roots=tuple(sorted(root.rstrip("\\/") or root for root in roots)),
        sep=os.sep,
        abspath=os.path.abspath,
        normcase=os.path.normcase,
        fsdecode=os.fsdecode,
        write_flags=(
            os.O_WRONLY
            | os.O_RDWR
            | os.O_APPEND
            | os.O_CREAT
            | os.O_TRUNC
            | getattr(os, "O_TEMPORARY", 0)
        ),
    )

    short_repr = make_short_repr()
    function_name = str(payload["function"])
    tests = [
        prepare_test(index, test, function_name, short_repr, ast.literal_eval)
        for index, test in enumerate(payload["tests"])
    ]
    try:
        code = compile(payload["source"], "<candidate>", "exec", dont_inherit=True)
        compile_error = None
    except (SyntaxError, ValueError, OverflowError, MemoryError, RecursionError) as exc:
        code = None
        compile_error = describe_exception(exc)
    namespace = {
        "__builtins__": {
            name: value for name, value in vars(builtins).items() if name not in REMOVED_BUILTINS
        },
        "__name__": "candidate",
    }
    emit(
        {
            "t": "ready",
            "limits": limits_applied,
            "hook": NO_HOOK_FLAG not in argv,
            "env": environment,
            "cwd_ok": cwd_ok,
            "pid": os.getpid(),
        }
    )

    state["phase"] = "run"
    if code is None:
        emit({"t": "defined", "ok": False, "d": f"The candidate does not compile: {compile_error}"})
        emit({"t": "final"})
        return 0
    try:
        exec(code, namespace)
    except BaseException as exc:  # a default value or annotation may raise anything
        emit(
            {
                "t": "defined",
                "ok": False,
                "d": f"Defining the candidate raised {describe_exception(exc)}",
            }
        )
        emit({"t": "final"})
        return 0
    func = namespace.get(function_name)
    if not isinstance(func, types.FunctionType):
        emit(
            {
                "t": "defined",
                "ok": False,
                "d": f"The candidate does not define a function named {function_name}.",
            }
        )
        emit({"t": "final"})
        return 0
    emit({"t": "defined", "ok": True})
    for index, prepared in enumerate(tests):
        if prepared["error"] is not None:
            emit({"t": "test", "i": index, "k": "runner_error", "d": prepared["error"]})
            continue
        kind, detail = evaluate(prepared, func, short_repr)
        emit(
            {"t": "test", "i": index, "k": kind, "d": None if detail is None else _truncate(detail)}
        )
    emit({"t": "final"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

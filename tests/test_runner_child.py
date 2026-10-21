"""Unit tests of the test-process helpers and of the result mapping.

The audit hook is exercised by calling it directly; it is never installed in this
process (an installed audit hook cannot be removed). No candidate code runs here.
"""

import ast
import os

import pytest

from refactor_ai.contracts import ReferenceCase, ReferenceTest
from refactor_ai.verification import runner_child as child
from refactor_ai.verification.runner import Execution, RunnerLimits, _to_result

# --- Audit hook policy table --------------------------------------------------------


ROOT = os.path.normcase(os.path.abspath(os.path.join("runner-policy-test", "lib")))
OUTSIDE = os.path.abspath(os.path.join("runner-policy-test", "home", "secret.txt"))


@pytest.fixture
def state():
    """Hook state with a fictitious library root; the hook only normalizes paths."""
    root = ROOT
    return {
        "phase": "run",
        "roots": (root,),
        "sep": os.sep,
        "abspath": os.path.abspath,
        "normcase": os.path.normcase,
        "fsdecode": os.fsdecode,
        "write_flags": os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC,
        "root": root,
    }


ALWAYS_BLOCKED = [
    "socket.__new__",
    "socket.connect",
    "socket.getaddrinfo",
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "os.fork",
    "os.forkpty",
    "os.startfile",
    "os.kill",
    "os.killpg",
    "ctypes.dlopen",
    "ctypes.cdata",
    "_winapi.CreateProcess",
    "_winapi.CreateFile",
    "winreg.OpenKey",
    "msvcrt.open_osfhandle",
    "os.remove",
    "os.rename",
    "os.mkdir",
    "os.rmdir",
    "os.chdir",
    "os.chmod",
    "os.putenv",
    "os.unsetenv",
    "os.symlink",
    "os.truncate",
    "os.utime",
    "os.walk",
    "shutil.rmtree",
    "tempfile.mkstemp",
    "sys.addaudithook",
    "_thread.start_new_thread",
    "webbrowser.open",
    "urllib.Request",
    "http.client.connect",
    "sqlite3.connect",
    "mmap.__new__",
    "builtins.input",
    "builtins.breakpoint",
    "signal.pthread_kill",
    "glob.glob",
    "pathlib.Path.glob",
    "setopencode",
]
RUN_BLOCKED = [
    "sys._getframe",
    "sys._current_frames",
    "sys.settrace",
    "sys.setprofile",
    "object.__getattr__",
    "gc.get_objects",
    "gc.get_referrers",
    "function.__new__",
    "code.__new__",
    "resource.setrlimit",
]
ALLOWED = [
    "exec",
    "compile",
    "marshal.loads",
    "builtins.id",
    "object.__setattr__",
    "time.sleep",
    "cpython._PySys_ClearAuditHooks",
]


@pytest.mark.parametrize("phase", ["setup", "run"])
@pytest.mark.parametrize("event", ALWAYS_BLOCKED)
def test_blocked_in_every_phase(state, phase, event):
    state["phase"] = phase
    with pytest.raises(child.RunnerPolicyError):
        child.make_audit_hook(state)(event, ())


@pytest.mark.parametrize("event", RUN_BLOCKED)
def test_blocked_once_candidate_code_runs(state, event):
    hook = child.make_audit_hook(state)
    state["phase"] = "setup"
    hook(event, ())
    state["phase"] = "run"
    with pytest.raises(child.RunnerPolicyError):
        hook(event, ())


@pytest.mark.parametrize("event", ALLOWED)
def test_interpreter_events_stay_allowed(state, event):
    child.make_audit_hook(state)(event, ())


@pytest.mark.parametrize(
    ("module", "blocked"),
    [
        ("socket", True),
        ("_socket", True),
        ("ctypes", True),
        ("ctypes.util", True),
        ("subprocess", True),
        ("multiprocessing.pool", True),
        ("_winapi", True),
        ("importlib", True),
        (None, True),
        ("encodings.cp1252", False),
        ("json", False),
        ("math", False),
    ],
)
def test_import_policy(state, module, blocked):
    hook = child.make_audit_hook(state)
    args = (module, None, [], [], [])
    if blocked:
        with pytest.raises(child.RunnerPolicyError):
            hook("import", args)
    else:
        hook("import", args)
    state["phase"] = "setup"
    hook("import", args)  # the trusted setup may import anything


def test_file_access_policy(state):
    hook = child.make_audit_hook(state)
    inside = os.path.join(state["root"], "encodings", "x.pyc")
    outside = OUTSIDE
    hook("open", (inside, "r", 0))
    hook("open", (inside.encode(), "rb", 0))
    hook("open", (inside, None, os.O_RDONLY))
    hook("os.listdir", (state["root"],))
    hook("os.scandir", (os.path.join(state["root"], "encodings"),))
    for args in [
        (outside, "r", 0),
        (inside, "w", 0),
        (inside, "a", 0),
        (inside, "x", 0),
        (inside, "r+", 0),
        (inside, None, os.O_WRONLY | os.O_CREAT),
        (inside, None, os.O_RDWR),
        (inside, None, "bad flags"),
        (1, "w", 0),
        (3, "r", 0),
        (None, "r", 0),
        (state["root"] + "-sibling" + os.sep + "x", "r", 0),
    ]:
        with pytest.raises(child.RunnerPolicyError):
            hook("open", args)
    with pytest.raises(child.RunnerPolicyError):
        hook("os.listdir", (os.path.dirname(OUTSIDE),))
    state["phase"] = "setup"
    hook("open", (outside, "w", 0))  # setup redirects descriptor 1 to the null device


# --- Comparison and reporting helpers --------------------------------------------------


@pytest.mark.parametrize(
    ("expected", "actual", "same"),
    [
        (0.3, 0.1 + 0.2, True),
        (1.0, 1.0 + 1e-10, True),
        (1.0, 1.0 + 1e-8, False),
        (0.0, 1e-17, False),
        (float("inf"), float("inf"), True),
        (1.0, float("nan"), False),
        (1, 1.0, False),
        (1, True, False),
        (True, True, True),
        ("a", "a", True),
        (b"a", "a", False),
        ([1, 2.0], [1, 2.0000000001], True),
        ([1, 2], (1, 2), False),
        ((1, [2.0]), (1, [2.0]), True),
        ([1, 2], [1, 2, 3], False),
        ({"a": 1.0}, {"a": 1.0 + 1e-12}, True),
        ({"a": 1}, {"b": 1}, False),
        ({1: "x"}, {True: "x"}, False),
        ({1, 2}, {2, 1}, True),
        (frozenset({1}), {1}, False),
        (1 + 2j, 1 + 2.0000000001j, True),
        (None, None, True),
        (None, 0, False),
    ],
)
def test_same_value(expected, actual, same):
    assert child.same_value(expected, actual) is same


def test_same_value_depth_limit():
    deep = current = []
    for _ in range(60):
        nxt = []
        current.append(nxt)
        current = nxt
    assert child.same_value(deep, deep) is False


def test_short_repr_is_bounded():
    short = child.make_short_repr()
    assert short(list(range(100))) == "[0, 1, 2, 3, 4, 5, 6, 7, ...]"
    assert len(short("x" * 1000)) < 100
    assert short(10**5000) == "<int value>"


def test_describe_exception_is_bounded_and_safe():
    assert child.describe_exception(ValueError("bad")) == "ValueError: bad"
    assert child.describe_exception(KeyError()) == "KeyError"
    assert len(child.describe_exception(ValueError("x" * 1000))) <= 200

    class Unprintable(Exception):
        def __str__(self):
            raise RuntimeError("no")

    assert child.describe_exception(Unprintable()) == "Unprintable"


def prepare(**test):
    data = {"args": "[]", "kwargs": "{}", "kind": "return", "value": "None", "exception": None}
    data.update(test)
    return child.prepare_test(0, data, "f", child.make_short_repr(), ast.literal_eval)


def test_prepare_test_parses_literals():
    prepared = prepare(args="[1, 'a']", kwargs="{'b': (2,)}", value="[3]")
    assert prepared["error"] is None
    assert prepared["args"] == (1, "a") and prepared["kwargs"] == {"b": (2,)}
    assert prepared["expected"] == [3]
    assert prepared["call"] == "f(1, 'a', b=(2,))"
    raised = prepare(kind="raise", exception=" ValueError ", value=None)
    assert raised["exception"] == "ValueError"


@pytest.mark.parametrize(
    ("test", "message"),
    [
        ({"args": "1"}, "args must be a list or tuple"),
        ({"args": "[os.sep]"}, "ValueError"),
        ({"kwargs": "{1: 2}"}, "string keys"),
        ({"kwargs": "[]"}, "string keys"),
        ({"value": None}, "needs a literal value"),
        ({"value": "float('nan')"}, "ValueError"),
        ({"kind": "raise", "exception": None}, "exception type name"),
        ({"kind": "raise", "exception": "  "}, "exception type name"),
        ({"kind": "yield"}, "unknown expectation kind"),
    ],
)
def test_prepare_test_reports_bad_case_data(test, message):
    prepared = prepare(**test)
    assert prepared["error"].startswith("Test 0 could not be prepared")
    assert message in prepared["error"]


def outcome_of(func, **test):
    return child.evaluate(prepare(**test), func, child.make_short_repr())


def test_evaluate_outcomes():
    assert outcome_of(lambda: 3, value="3") == ("pass", None)
    assert outcome_of(lambda: 3.0, value="3")[0] == "wrong_value"
    kind, detail = outcome_of(lambda: 4, value="3")
    assert kind == "wrong_value" and detail == "f() returned 4 (int); expected 3 (int)."

    def raises():
        raise ValueError("no")

    assert outcome_of(raises, kind="raise", exception="ValueError") == ("pass", None)
    kind, detail = outcome_of(raises, kind="raise", exception="TypeError")
    assert kind == "wrong_exception" and detail == "f() raised ValueError: no; expected TypeError."
    kind, detail = outcome_of(raises, value="1")
    assert kind == "unexpected_exception" and "expected the return value 1" in detail
    kind, detail = outcome_of(lambda: 0, kind="raise", exception="ValueError")
    assert kind == "missing_exception" and "expected ValueError to be raised" in detail

    def exits():
        raise SystemExit(3)

    assert outcome_of(exits, value="1")[0] == "unexpected_exception"
    assert outcome_of(raises, kind="raise", exception="Exception")[0] == "wrong_exception"


def test_removed_builtins_are_the_denied_ones():
    from refactor_ai.tasks import guard_clauses

    assert set(guard_clauses.DENIED_CALLS) - {"__import__"} <= set(child.REMOVED_BUILTINS)
    assert "__import__" not in child.REMOVED_BUILTINS


# --- Result mapping ----------------------------------------------------------------------

CASE = ReferenceCase(
    case_id="c",
    task_type="guard_clauses",
    function_name="f",
    original_code="def f():\n    return 1\n",
    tests=[ReferenceTest(expect={"kind": "return", "value": "1"}) for _ in range(3)],
)
LIMITS = RunnerLimits(wall_timeout_s=5.0, cpu_time_s=2.0, memory_mb=128)
READY = {"t": "ready", "limits": "job", "hook": True, "env": [], "cwd_ok": True, "pid": 1}
DEFINED = {"t": "defined", "ok": True}
FINAL = {"t": "final"}


def test_event(index, kind="pass", detail=None):
    return {"t": "test", "i": index, "k": kind, "d": detail}


test_event.__test__ = False  # a helper, not a test


def mapped(outcome="completed", events=(), **fields):
    return _to_result(CASE, Execution(outcome=outcome, events=list(events), **fields), 5.0, LIMITS)


def test_all_tests_pass():
    result = mapped(events=[READY, DEFINED, *[test_event(i) for i in range(3)], FINAL])
    assert (result.status, result.passed, result.failed, result.errored) == ("pass", 3, 0, 0)
    assert result.reason is None and result.failures == []


def test_failures_and_errors_are_counted():
    events = [
        READY,
        DEFINED,
        test_event(0),
        test_event(1, "wrong_value", "f() returned 2"),
        test_event(2, "runner_error", "bad data"),
        FINAL,
    ]
    result = mapped(events=events)
    assert (result.status, result.passed, result.failed, result.errored) == ("fail", 1, 1, 1)
    assert [(f.index, f.kind) for f in result.failures] == [(1, "wrong_value"), (2, "runner_error")]


def test_only_runner_errors_is_an_error():
    events = [READY, DEFINED, test_event(0), test_event(1), test_event(2, "runner_error"), FINAL]
    assert mapped(events=events).status == "error"


def test_missing_function_fails_every_test():
    result = mapped(events=[READY, {"t": "defined", "ok": False, "d": "no f"}, FINAL])
    assert (result.status, result.passed, result.failed) == ("fail", 0, 3)
    assert result.failures[0].kind == "missing_function" and result.failures[0].detail == "no f"


@pytest.mark.parametrize("outcome", ["timeout", "cpu_limit"])
def test_limit_during_a_test(outcome):
    result = mapped(outcome, events=[READY, DEFINED, test_event(0)])
    assert (result.status, result.passed, result.failed) == ("fail", 1, 1)
    failure = result.failures[-1]
    assert failure.kind == "timeout" and failure.index == 1
    limit = "2 s CPU time limit" if outcome == "cpu_limit" else "5 s wall-clock limit"
    assert limit in failure.detail and "1 later tests were not run" in failure.detail


def test_limit_while_defining_the_function():
    result = mapped("timeout", events=[READY])
    assert (result.status, result.failed) == ("fail", 3)
    assert result.failures[0].kind == "timeout" and "Defining the function" in result.reason


def budget_mapped(outcome="timeout", events=()):
    """The wall-clock limit was lowered to the 0.4 s left in the workflow run."""
    execution = Execution(outcome=outcome, events=list(events))
    return _to_result(CASE, execution, 0.4, LIMITS, budget_limited=True)


@pytest.mark.parametrize(
    ("events", "where"),
    [
        ([], "before the test process was ready"),
        ([READY], "while the function was being defined"),
        ([READY, DEFINED], "before the first test finished"),
        ([READY, DEFINED, test_event(0), test_event(1)], "after 2 of 3 tests had passed"),
    ],
    ids=["not-ready", "defining", "first-test", "later-test"],
)
def test_run_budget_ending_is_not_blamed_on_the_candidate(events, where):
    result = budget_mapped(events=events)
    assert result.status == "not_run" and result.failures == []
    assert (result.passed, result.failed, result.errored) == (None, None, None)
    assert "time limit left only 0.4 s for the reference tests" in result.reason
    assert where in result.reason


def test_run_budget_ending_keeps_failures_already_observed():
    events = [READY, DEFINED, test_event(0, "wrong_value", "f() returned 2")]
    result = budget_mapped(events=events)
    assert (result.status, result.passed, result.failed, result.errored) == ("fail", 0, 1, 0)
    assert [(f.index, f.kind) for f in result.failures] == [(0, "wrong_value")]
    assert "1 of 3 reference tests failed" in result.reason and "0.4 s" in result.reason


def test_run_budget_ending_keeps_runner_errors_already_observed():
    result = budget_mapped(events=[READY, DEFINED, test_event(0), test_event(1, "runner_error")])
    assert (result.status, result.passed, result.errored) == ("error", 1, 1)
    assert [(f.index, f.kind) for f in result.failures] == [(1, "runner_error")]


def test_own_cpu_limit_still_fails_under_a_run_budget():
    result = budget_mapped("cpu_limit", events=[READY, DEFINED, test_event(0)])
    assert (result.status, result.passed, result.failed) == ("fail", 1, 1)
    assert result.failures[-1].kind == "timeout" and "2 s CPU time limit" in result.reason


def test_crash_during_a_test_is_an_error():
    result = mapped(
        events=[READY, DEFINED, test_event(0)],
        exit_code=-11,
        peak_memory_bytes=128 * 1024 * 1024,
    )
    assert result.status == "error" and (result.passed, result.errored) == (1, 1)
    assert result.failures[-1].kind == "runner_error"
    assert "exit code -11" in result.reason and "memory limit was reached" in result.reason


@pytest.mark.parametrize(
    ("outcome", "events", "text"),
    [
        ("start_failed", [], "could not be started"),
        ("output_overflow", [READY], "more output"),
        ("completed", [{"t": "fatal", "d": "limits"}], "refused to run"),
        ("completed", [], "stopped before it was ready"),
        ("timeout", [], "before it was ready"),
        ("completed", [READY, DEFINED, test_event(1), FINAL], "out of order"),
        ("completed", [READY, DEFINED, test_event(0, "teleported"), FINAL], "unknown outcome"),
    ],
)
def test_protocol_problems_are_errors(outcome, events, text):
    result = mapped(outcome, events=events)
    assert result.status == "error" and text in result.reason


def test_failure_details_are_capped():
    case = CASE.model_copy(update={"tests": CASE.tests * 5})
    events = [READY, DEFINED] + [test_event(i, "wrong_value", "x" * 900) for i in range(15)]
    result = _to_result(case, Execution(outcome="completed", events=[*events, FINAL]), 5.0, LIMITS)
    assert len(result.failures) == 10 and result.failed == 15
    assert all(len(failure.detail) <= 500 for failure in result.failures)

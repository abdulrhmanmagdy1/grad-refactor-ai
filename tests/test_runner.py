"""Reference runner tests that start real, limited test processes.

They need the runner's isolation (Job Object on Windows, resource limits on Linux) and
run on both CI platforms; elsewhere they are skipped. Candidates that must be refused are
handed to the runner as text only. Probes that bypass the static policy go through
runner._execute so that the audit hook and the operating-system limits are tested on
their own.
"""

from __future__ import annotations

import os
import socket
import sys
import time

import pytest

from refactor_ai.agents import run_workflow
from refactor_ai.contracts import (
    Disposition,
    ModelReviewResult,
    ReferenceCase,
    ReferenceTest,
    RubricCheck,
    SyntaxCheck,
    WorkflowMode,
    WorkflowRequest,
    WorkflowSettings,
)
from refactor_ai.providers import FakeProvider
from refactor_ai.tasks import guard_clauses
from refactor_ai.verification import create_runner, decide, load_cases
from refactor_ai.verification.runner import (
    ALLOWED_CHILD_ENVIRONMENT,
    RunnerLimits,
    SubprocessReferenceRunner,
)

pytestmark = pytest.mark.skipif(
    sys.platform not in ("win32", "linux"), reason="The reference runner supports Windows and Linux"
)

SHIP = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight > 0:
        if express:
            return weight * 3
        else:
            return weight * 2
    else:
        raise ValueError("weight must be positive")
'''
GOOD = guard_clauses.to_guard_clauses(SHIP)


def returns(args: str, value: str, kwargs: str = "{}") -> ReferenceTest:
    return ReferenceTest(args=args, kwargs=kwargs, expect={"kind": "return", "value": value})


def raises(args: str, exception: str) -> ReferenceTest:
    return ReferenceTest(args=args, expect={"kind": "raise", "exception": exception})


CASE = ReferenceCase(
    case_id="shipping",
    task_type="guard_clauses",
    function_name="shipping_cost",
    original_code=SHIP,
    reference_code=GOOD,
    tests=[
        returns("[2, True]", "6"),
        returns("[2, False]", "4"),
        raises("[0, True]", "ValueError"),
        returns("[1.5]", "4.5", kwargs="{'express': True}"),
    ],
)
EXPECTED_CHECKS = {
    "platform_supported",
    "interpreter_found",
    "basic_execution",
    "os_limits_applied",
    "audit_hook_installed",
    "environment_scrubbed",
    "working_directory_isolated",
    "workdir_removed",
    "network_blocked",
    "file_write_blocked",
    "host_read_blocked",
    "subprocess_blocked",
    "native_code_blocked",
    "introspection_blocked",
    "process_limit_enforced",
    "memory_limit_enforced",
    "timeout_enforced",
    "process_cleanup",
    "cpu_limit_enforced",
}
LOOP = "def shipping_cost(weight, express):\n    while True:\n        weight += 1\n"


@pytest.fixture(scope="module")
def work_root(tmp_path_factory):
    return tmp_path_factory.mktemp("runner-work")


@pytest.fixture(scope="module")
def runner(work_root):
    runner = SubprocessReferenceRunner(
        RunnerLimits(wall_timeout_s=60.0, cpu_time_s=2.0, memory_mb=256), work_root=work_root
    )
    info = runner.info()
    assert info.enabled, info.reason
    return runner


def process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)  # SYNCHRONIZE, query
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT: running
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def probe(runner, source: str, tests, *, audit_hook: bool = True, function: str = "probe"):
    """Run probe code that bypasses the static policy, to test the dynamic layers."""
    return runner._execute(
        function,
        source,
        tests,
        wall_s=60.0,
        cpu_s=runner.limits.cpu_time_s,
        memory_mb=runner.limits.memory_mb,
        audit_hook=audit_hook,
    )


def outcomes(execution) -> list[tuple[str, str]]:
    return [(event["k"], event.get("d") or "") for event in execution.tests()]


# --- Isolation self-checks ---------------------------------------------------------


def test_self_checks_enable_execution(runner):
    info = runner.info()
    assert info.enabled is True and info.reason is None
    assert set(info.isolation) == EXPECTED_CHECKS
    assert all(info.isolation.values())


def test_disabled_runner_never_executes():
    runner = create_runner("disabled")
    info = runner.info()
    assert info.enabled is False and "disabled by configuration" in info.reason
    result = runner.run(CASE, GOOD)
    assert result.status == "not_run" and result.reason == info.reason
    assert runner.last_execution is None


def test_failed_self_checks_disable_execution(tmp_path):
    runner = SubprocessReferenceRunner(interpreter=str(tmp_path / "no-python.exe"))
    info = runner.info()
    assert info.enabled is False
    assert info.isolation["interpreter_found"] is False
    assert info.isolation["basic_execution"] is False
    assert info.reason.startswith("Isolation self-checks failed: ")
    assert "interpreter_found" in info.reason and "basic_execution" in info.reason
    result = runner.run(CASE, GOOD)
    assert result.status == "not_run" and result.reason == info.reason


def test_unusable_work_directory_is_a_runner_error(tmp_path):
    runner = SubprocessReferenceRunner(work_root=tmp_path / "missing")
    runner._info = runner_info_enabled()
    result = runner.run(CASE, GOOD)
    assert result.status == "error" and "could not be started" in result.reason
    assert runner.last_execution.outcome == "start_failed"


def test_create_runner_rejects_unknown_modes():
    with pytest.raises(ValueError):
        create_runner("sometimes")


# --- Outcomes -----------------------------------------------------------------------


def test_correct_candidate_passes(runner):
    result = runner.run(CASE, GOOD)
    assert result.status == "pass", result
    assert (result.total, result.passed, result.failed, result.errored) == (4, 4, 0, 0)
    assert result.case_id == "shipping" and result.duration_s > 0
    assert runner.run(CASE, CASE.reference_code).status == "pass"


def test_wrong_value(runner):
    result = runner.run(CASE, GOOD.replace("weight * 2", "weight * 5"))
    assert (result.status, result.passed, result.failed) == ("fail", 3, 1)
    failure = result.failures[0]
    assert failure.index == 1 and failure.kind == "wrong_value"
    assert failure.detail == "shipping_cost(2, False) returned 10 (int); expected 4 (int)."


def test_missing_exception(runner):
    result = runner.run(CASE, GOOD.replace("weight <= 0", "weight < 0"))
    assert result.status == "fail"
    assert [(f.index, f.kind) for f in result.failures] == [(2, "missing_exception")]


def test_wrong_exception(runner):
    result = runner.run(CASE, GOOD.replace("raise ValueError", "raise TypeError"))
    assert [(f.index, f.kind) for f in result.failures] == [(2, "wrong_exception")]
    assert (
        "raised TypeError: weight must be positive; expected ValueError"
        in result.failures[0].detail
    )


def test_unexpected_exception(runner):
    result = runner.run(CASE, GOOD.replace("return weight * 3", "return weight // 0"))
    kinds = [(f.index, f.kind) for f in result.failures]
    assert kinds == [(0, "unexpected_exception"), (3, "unexpected_exception")]
    assert "ZeroDivisionError" in result.failures[0].detail


def test_missing_function(runner):
    result = runner.run(CASE, GOOD.replace("def shipping_cost", "def cost"))
    assert (result.status, result.passed, result.failed) == ("fail", 0, 4)
    assert result.failures[0].kind == "missing_function"
    assert "does not define a function named shipping_cost" in result.failures[0].detail


def test_definition_error_is_a_missing_function(runner):
    result = runner.run(CASE, GOOD.replace("express):", "express=1 // 0):", 1))
    assert result.failures[0].kind == "missing_function"
    assert "Defining the candidate raised ZeroDivisionError" in result.failures[0].detail


def test_syntax_error_is_reported_without_starting_a_process(runner):
    before = runner.last_execution
    result = runner.run(CASE, "def shipping_cost(weight, express:\n    return 1\n")
    assert (result.status, result.failed) == ("fail", 4)
    assert result.failures[0].kind == "missing_function"
    assert "does not parse" in result.failures[0].detail
    assert runner.last_execution is before


def test_infinite_loop_hits_the_wall_clock_limit(runner, work_root):
    # The runner's own 1 s wall-clock limit, not a shorter run budget, stops the loop.
    short = SubprocessReferenceRunner(
        RunnerLimits(wall_timeout_s=1.0, cpu_time_s=2.0, memory_mb=256), work_root=work_root
    )
    short._info = runner.info()  # same host, so the fixture runner's self-checks apply
    started = time.monotonic()
    result = short.run(CASE, LOOP)
    assert time.monotonic() - started < 12.0
    assert result.status == "fail" and (result.passed, result.failed) == (0, 1)
    failure = result.failures[0]
    assert failure.kind == "timeout" and failure.index == 0
    assert (
        "1 s wall-clock limit" in failure.detail and "3 later tests were not run" in failure.detail
    )
    execution = short.last_execution
    assert execution.outcome == "timeout" and execution.cleanup_ok
    assert execution.workdir_removed and not os.path.exists(execution.workdir)
    assert not process_alive(execution.pid)


def single_role_disposition(tests) -> Disposition:
    return decide(
        SyntaxCheck(status="pass"),
        RubricCheck(status="pass"),
        tests,
        ModelReviewResult(status="not_run"),
        mode=WorkflowMode.SINGLE_ROLE,
    )[0]


def test_run_budget_ending_during_the_tests_is_not_a_failure(runner):
    # The workflow lowers the wall-clock limit to the time left in the run; when that
    # shorter limit ends the process, the tests did not finish, the candidate did not fail.
    result = runner.run(CASE, LOOP, timeout_s=1.0)
    assert result.status == "not_run" and result.failures == [], result
    assert "time limit left only 1 s for the reference tests" in result.reason
    execution = runner.last_execution
    assert execution.outcome == "timeout" and execution.cleanup_ok
    assert not process_alive(execution.pid)
    assert single_role_disposition(result) == Disposition.UNCERTAIN


def test_correct_candidate_is_not_rejected_when_the_run_budget_is_tiny(runner):
    # About 0.3 s of interpreter start on the laptop exceeds the 0.05 s left in the run.
    # A fast host may still finish all four tests; either way it is never a rejection.
    result = runner.run(CASE, GOOD, timeout_s=0.05)
    assert result.status in ("not_run", "pass"), result
    assert single_role_disposition(result) != Disposition.REJECTED


def test_cpu_bound_loop_hits_the_cpu_limit(runner):
    # The 60 s wall-clock limit leaves room for a busy machine; the 2 s CPU limit stops it.
    result = runner.run(CASE, LOOP)
    assert result.status == "fail"
    assert result.failures[0].kind == "timeout"
    assert "2 s CPU time limit" in result.failures[0].detail
    assert runner.last_execution.outcome == "cpu_limit"
    assert not process_alive(runner.last_execution.pid)


def test_memory_bomb_is_stopped_by_the_memory_limit(runner):
    bomb = (
        "def shipping_cost(weight, express):\n"
        "    blocks = []\n"
        "    while True:\n"
        "        blocks.append(bytearray(10 ** 6))\n"
    )
    case = CASE.model_copy(update={"tests": CASE.tests[:2]})
    result = runner.run(case, bomb)
    assert result.status == "fail", result
    assert [failure.kind for failure in result.failures] == ["unexpected_exception"] * 2
    assert all("MemoryError" in failure.detail for failure in result.failures)


def test_comparison_semantics(runner):
    source = """def convert(kind):
    if kind == "float":
        return 0.1 + 0.2
    if kind == "int":
        return 1
    if kind == "bool":
        return True
    if kind == "tuple":
        return (1, 2)
    if kind == "nested":
        return {"a": [1.0000000001, 2]}
    return None
"""
    case = ReferenceCase(
        case_id="convert",
        task_type="guard_clauses",
        function_name="convert",
        original_code=source,
        tests=[
            returns("['float']", "0.3"),
            returns("['int']", "1.0"),
            returns("['bool']", "1"),
            returns("['tuple']", "[1, 2]"),
            returns("['nested']", "{'a': [1.0, 2]}"),
            returns("['other']", "None"),
            returns("[]", "1", kwargs="{'kind': 'int'}"),
            returns("[os.sep]", "None"),
            raises("['int']", "Exception"),
        ],
    )
    result = runner.run(case, source)
    kinds = {failure.index: failure.kind for failure in result.failures}
    assert kinds == {
        1: "wrong_value",
        2: "wrong_value",
        3: "wrong_value",
        7: "runner_error",
        8: "missing_exception",
    }
    assert (result.status, result.passed, result.failed, result.errored) == ("fail", 4, 4, 1)


# --- Refusals ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("candidate", "text"),
    [
        (
            "def shipping_cost(weight, express):\n    import socket\n"
            "    return socket.gethostname()\n",
            "Imports are outside",
        ),
        (
            "def shipping_cost(weight, express):\n    open('x.txt', 'w').write('x')\n"
            "    return 1\n",
            "Calls to open()",
        ),
        ("import subprocess\n" + GOOD, "exactly one top-level function"),
        (
            "def shipping_cost(weight, express):\n"
            "    return getattr(weight, '_' * 2 + 'class' + '_' * 2)\n",
            "literal attribute name",
        ),
        ("def shipping_cost(weight, express):\n    run = eval\n    return run('1')\n", "eval"),
    ],
)
def test_policy_refuses_candidates_before_execution(runner, candidate, text):
    before = runner.last_execution
    result = runner.run(CASE, candidate)
    assert result.status == "not_run" and text in result.reason
    assert runner.last_execution is before


def test_invalid_requests():
    runner = SubprocessReferenceRunner()
    runner._info = runner_info_enabled()
    other = CASE.model_copy(update={"task_type": "extract_method"})
    assert runner.run(other, GOOD).status == "error"
    assert runner.run(CASE, "x" * 30_000).status == "not_run"
    assert runner.run(CASE, GOOD, timeout_s=0).status == "not_run"
    empty = CASE.model_copy(update={"tests": []})
    assert runner.run(empty, GOOD).status == "not_available"
    assert runner.last_execution is None


def runner_info_enabled():
    from refactor_ai.contracts import RunnerInfo

    return RunnerInfo(enabled=True)


# --- Dynamic layers (static policy bypassed on purpose) ------------------------------


def test_audit_hook_blocks_network(runner):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.setblocking(False)
    port = listener.getsockname()[1]
    try:
        source = (
            "def probe(port):\n    import socket\n"
            "    socket.create_connection(('127.0.0.1', port), timeout=3).close()\n"
            "    return 'connected'\n"
        )
        execution = probe(runner, source, [returns(f"[{port}]", "'connected'")])
        with pytest.raises(BlockingIOError):
            listener.accept()
    finally:
        listener.close()
    kind, detail = outcomes(execution)[0]
    assert kind == "unexpected_exception" and "RunnerPolicyError" in detail


def test_audit_hook_blocks_file_writes_and_host_reads(runner, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    target = tmp_path / "written.txt"
    source = (
        "def probe(kind, path):\n    import io\n    import os\n"
        "    if kind == 'write':\n        io.open(path, 'w').close()\n"
        "    if kind == 'os_write':\n        os.close(os.open(path, os.O_WRONLY | os.O_CREAT))\n"
        "    if kind == 'read':\n        return io.open(path).read()\n"
        "    if kind == 'relative':\n        io.open('inside.txt', 'w').close()\n"
        "    return 'done'\n"
    )
    tests = [
        returns(repr(["write", str(target)]), "'done'"),
        returns(repr(["os_write", str(target)]), "'done'"),
        returns(repr(["read", str(secret)]), "'not the secret'"),
        returns(repr(["relative", ""]), "'done'"),
    ]
    execution = probe(runner, source, tests)
    results = outcomes(execution)
    assert all(
        kind == "unexpected_exception" and "RunnerPolicyError" in detail for kind, detail in results
    )
    assert not target.exists()
    assert "top secret" not in execution.raw_stdout.decode()


def test_audit_hook_blocks_processes_and_native_code(runner, tmp_path):
    # Probe text runs only inside the isolated test process, where subprocess, os.system,
    # ctypes and frame access must all be refused; the test fails if any succeeds.
    marker = tmp_path / "spawned.txt"
    command = [runner.interpreter, "-c", f"open({str(marker)!r}, 'w').close()"]
    source = (
        "def probe(kind, command):\n"
        "    if kind == 'subprocess':\n        import subprocess\n        subprocess.run(command)\n"
        "    if kind == 'system':\n        import os\n        os.system('exit 0')\n"
        "    if kind == 'ctypes':\n        import ctypes\n"
        "    if kind == 'frame':\n        return (item for item in [1]).gi_frame is not None\n"
        "    return 'done'\n"
    )
    tests = [
        returns(repr(["subprocess", command]), "'done'"),
        returns(repr(["system", None]), "'done'"),
        returns(repr(["ctypes", None]), "'done'"),
        returns(repr(["frame", None]), "'done'"),
    ]
    results = outcomes(probe(runner, source, tests))
    assert all(
        kind == "unexpected_exception" and "RunnerPolicyError" in detail for kind, detail in results
    )
    assert not marker.exists()


def test_operating_system_blocks_child_processes_without_the_hook(runner, tmp_path):
    marker = tmp_path / "spawned.txt"
    command = [runner.interpreter, "-c", f"open({str(marker)!r}, 'w').close()"]
    source = (
        "def probe(command):\n    import subprocess\n    subprocess.run(command)\n"
        "    return 'spawned'\n"
    )
    execution = probe(runner, source, [returns(repr([command]), "'spawned'")], audit_hook=False)
    assert execution.first("ready")["hook"] is False
    kind, detail = outcomes(execution)[0]
    assert kind == "unexpected_exception" and "RunnerPolicyError" not in detail
    assert not marker.exists()
    assert execution.cleanup_ok


def test_introspection_is_blocked_even_when_the_policy_admits_the_code(runner):
    candidate = (
        "def shipping_cost(weight, express):\n"
        "    frames = (item for item in [weight]).gi_frame\n"
        "    return frames\n"
    )
    result = runner.run(CASE.model_copy(update={"tests": CASE.tests[:1]}), candidate)
    assert result.failures[0].kind == "unexpected_exception"
    assert "RunnerPolicyError" in result.failures[0].detail


def test_result_channel_cannot_be_forged(runner):
    forged = '0123 {"t": "test", "i": 0, "k": "pass", "d": null}\n'
    source = (
        f"def probe():\n    import os\n    os.write(1, {forged.encode()!r})\n    return 'not six'\n"
    )
    execution = probe(runner, source, [returns("[]", "6")])
    assert outcomes(execution) == [
        ("wrong_value", "probe() returned 'not six' (str); expected 6 (int).")
    ]
    lines = [line for line in execution.raw_stdout.split(b"\n") if line]
    assert len(lines) == len(execution.events)


def test_environment_is_scrubbed_and_workdirs_removed(runner, work_root, monkeypatch):
    monkeypatch.setenv("REFACTOR_AI_TEST_SECRET", "must-not-reach-the-child")
    runner.run(CASE, GOOD)
    ready = runner.last_execution.first("ready")
    assert set(ready["env"]) <= ALLOWED_CHILD_ENVIRONMENT
    assert "REFACTOR_AI_TEST_SECRET" not in ready["env"]
    assert ALLOWED_CHILD_ENVIRONMENT == (
        {"SYSTEMROOT"} if sys.platform == "win32" else {"LC_CTYPE"}
    )
    assert ready["cwd_ok"] is True and ready["hook"] is True
    assert ready["limits"] == ("job" if sys.platform == "win32" else "rlimit")
    assert list(work_root.iterdir()) == []


def test_common_operations_are_not_blocked(runner):
    source = """def probe(text):
    encoded = text.encode("idna") + text.encode("utf-16") + text.encode("punycode")
    decoded = encoded.decode("latin-1")
    words = sorted(set(text.split()), key=lambda word: (len(word), word))
    table = {word: index for index, word in enumerate(words)}
    total = sum(float(value) for value in ["1.5", "2.25"]) + int("12", 8)
    message = f"{total:.2f} {len(decoded)} {max(table.values())} {round(2.675, 2)}"
    return "{:>12}|{}".format(message, "%s-%d" % ("x", 3))
"""
    execution = probe(runner, source, [returns("['b a ab']", "'13.75 27 2 2.67|x-3'")])
    assert outcomes(execution) == [("pass", "")]


# --- Shipped demonstration cases ------------------------------------------------------


SHIPPED = load_cases()


@pytest.mark.parametrize("case", SHIPPED, ids=[case.case_id for case in SHIPPED])
def test_shipped_cases_pass_with_their_original_and_reference_code(runner, case):
    for code in (case.original_code, case.reference_code):
        result = runner.run(case, code)
        assert result.status == "pass", (case.case_id, result)
        assert result.passed == result.total == len(case.tests)


@pytest.mark.parametrize("mode", ["multi_role", "single_role"])
@pytest.mark.parametrize("case", SHIPPED, ids=[case.case_id for case in SHIPPED])
def test_shipped_cases_through_the_workflow(runner, case, mode):
    # Fake provider: the deterministic transformation, not a model.
    outcome = run_workflow(
        WorkflowRequest(code=case.original_code, task_type=case.task_type, reference_case=case),
        provider=FakeProvider(),
        settings=WorkflowSettings(mode=mode),
        runner=runner,
    )
    if guard_clauses.check_input(case.original_code).supported:
        assert outcome.verification.disposition == Disposition.PROPOSAL_READY, outcome
        assert outcome.verification.reference_tests.passed == len(case.tests)
    else:
        assert outcome.verification.disposition == Disposition.NO_CHANGE


def test_privilege_drop_only_under_root(monkeypatch):
    from refactor_ai.verification import runner as runner_module

    monkeypatch.setattr(runner_module.os, "geteuid", lambda: 0, raising=False)
    assert runner_module.privilege_drop() == {
        "user": runner_module.UNPRIVILEGED_ID,
        "group": runner_module.UNPRIVILEGED_ID,
        "extra_groups": [],
    }
    monkeypatch.setattr(runner_module.os, "geteuid", lambda: 1000, raising=False)
    assert runner_module.privilege_drop() == {}
    monkeypatch.delattr(runner_module.os, "geteuid", raising=False)
    assert runner_module.privilege_drop() == {}


def test_attribute_builtins_cannot_be_aliased_or_passed_as_values():
    from refactor_ai.verification.policy import admission_problems

    alias = 'def f(x):\n    g = getattr\n    return g(x, "_" + "_class__")\n'
    passed = 'def f(x):\n    return list(map(getattr, [x], ["__class__"]))[0]\n'
    assert "denied_name:getattr" in admission_problems(alias)
    assert "denied_name:getattr" in admission_problems(passed)
    assert admission_problems('def f(x):\n    return getattr(x, "real")\n') == []

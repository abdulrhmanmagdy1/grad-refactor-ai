"""Curation-only executor: outcomes, tracing, budgets, isolation and failure handling."""

import ast
import os
from pathlib import Path

import pytest

from refactor_ai.data import refgen
from refactor_ai.data.executor import Job, run_jobs

CODE = """def f(x, items=[]):
    items.append(x)
    if x > 3:
        raise ValueError('big')
    if x == 2:
        return {'a': [1, 2.5]}
    if x == 1:
        return len(items)
    if x == 0:
        while True:
            pass
    return float('inf') if x == -1 else (x, 'a')
"""


def call(value) -> tuple[str, str]:
    return (repr([value]), "{}")


def run_one(code, calls, mode="outcome", **kwargs):
    return run_jobs([Job("j", code, "f", tuple(calls), mode)], **kwargs)["j"]


def test_outcomes_lines_budget_and_fresh_defaults():
    result = run_one(CODE, [call(v) for v in (0, 1, 2, 4, -1, -2, "a")], "lines", line_budget=5000)
    assert result.error is None
    timeout, length, mapping, raised, inf, plain, incidental = result.results
    assert timeout["kind"] == "timeout"
    assert length == {"kind": "return", "value": "1", "type": "int", "lines": [2, 3, 5, 7, 8]}
    assert mapping["value"] == "{'a': [1, 2.5]}" and mapping["type"] == "dict"
    assert raised["kind"] == "raise" and raised["exception"] == "ValueError"
    assert raised["line"] == 4 and 4 in raised["lines"]
    assert inf["kind"] == "unrepresentable"
    assert plain["value"] == "(-2, 'a')"
    # Comparing 'a' > 3 fails inside the function on line 3, not at a raise statement.
    assert incidental["kind"] == "raise" and incidental["exception"] == "TypeError"
    assert incidental["line"] == 3


def test_branch_probes_record_truth_values():
    code = (
        "def f(x):\n    if x > 0:\n        return 1\n    if x == 0:\n        return 0\n"
        "    return -1\n"
    )
    instrumented, count = refgen.instrument_branches(code)
    assert count == 2
    result = run_one(instrumented, [call(1), call(0), call(-5)], "branches")
    assert [r["branches"] for r in result.results] == [
        [[0, True]],
        [[0, False], [1, True]],
        [[0, False], [1, False]],
    ]
    assert [r["value"] for r in result.results] == ["1", "0", "-1"]


def test_environment_and_working_directory_are_isolated(monkeypatch):
    monkeypatch.setenv("CURATION_TEST_SECRET", "should-not-leak")
    code = (
        "import os\n"
        "def f(x):\n"
        "    return (os.environ.get('CURATION_TEST_SECRET'), os.environ.get('PYTHONHASHSEED'),"
        " os.getcwd())\n"
    )
    result = run_one(code, [call(0)], hash_seed=7)
    secret, seed, cwd = ast.literal_eval(result.results[0]["value"])
    assert secret is None and seed == "7"
    assert Path(cwd).resolve() != Path.cwd().resolve()
    assert not Path(cwd).exists()  # the temporary working directory was removed


def test_hash_seed_makes_outcomes_reproducible():
    code = "def f(x):\n    return hash(x) % 1000003\n"
    first = run_one(code, [call("abc")], hash_seed=0).results[0]
    again = run_one(code, [call("abc")], hash_seed=0).results[0]
    assert first == again


def test_crashing_and_hanging_jobs_are_isolated():
    good = Job("good", "def f(x):\n    return x + 1\n", "f", (call(1),), "outcome")
    crash = Job("crash", "import os\ndef f(x):\n    os._exit(3)\n", "f", (call(1),), "outcome")
    hang = Job("hang", "import time\ndef f(x):\n    time.sleep(30)\n", "f", (call(1),), "outcome")
    results = run_jobs(
        [good, crash, hang], batch_size=3, workers=1, batch_timeout_s=8, job_timeout_s=3
    )
    assert results["good"].error is None and results["good"].results[0]["value"] == "2"
    assert "harness" in results["crash"].error
    assert results["hang"].error == "wall-clock timeout"


def test_compile_errors_are_reported_per_job():
    results = run_jobs([Job("bad", "def f(:\n", "f", (call(1),), "outcome")])
    assert results["bad"].error.startswith("compile failed")


def test_job_ids_must_be_unique():
    job = Job("same", "def f(x):\n    return x\n", "f", (call(1),))
    with pytest.raises(ValueError, match="unique"):
        run_jobs([job, job])


def test_parent_environment_is_untouched():
    before = dict(os.environ)
    run_one("def f(x):\n    return x\n", [call(1)])
    assert dict(os.environ) == before

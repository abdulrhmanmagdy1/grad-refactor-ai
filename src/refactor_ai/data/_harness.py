"""Curation-only execution harness. Runs in a separate interpreter, never in the API.

The parent (refactor_ai.data.executor) passes this file's source with ``python -S -P -c``
and a JSON job list on stdin. Only trusted code is executed: functions from the team's
template families, functions from licensed datasets that passed the task's static
checks, and their deterministic reference transformations or mutants. Standard library
only. For every call the function definition is executed again in a fresh namespace so
mutable defaults cannot leak between calls; arguments are rebuilt with
ast.literal_eval. A line-event budget enforced through sys.settrace stops runaway loops
deterministically ("timeout"); the parent also applies a wall-clock timeout.
"""

import ast
import builtins
import json
import sys

PROBE = "_curation_branch_probe"
MAX_VALUE_CHARS = 300


class _Budget(BaseException):
    """Raised by the tracer when a call exceeds its line-event budget."""


_PARSED = {}


def _literal(source):
    """Fresh objects for every call; the parsed expression is cached per source text."""
    node = _PARSED.get(source)
    if node is None:
        node = _PARSED[source] = ast.parse(source, mode="eval")
    return ast.literal_eval(node)


def _same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, dict):
        if len(left) != len(right):
            return False
        return all(
            _same(ka, kb) and _same(va, vb)
            for (ka, va), (kb, vb) in zip(left.items(), right.items(), strict=True)
        )
    return left == right


def _return_outcome(value):
    try:
        text = repr(value)
    except Exception as exc:  # any repr failure makes the value unusable
        return {"kind": "unrepresentable", "detail": f"repr failed: {type(exc).__name__}"}
    if len(text) > MAX_VALUE_CHARS:
        return {"kind": "unrepresentable", "detail": "value too long"}
    try:
        restored = ast.literal_eval(text)
    except Exception:  # not a Python literal
        return {"kind": "unrepresentable", "detail": "not a literal"}
    if not _same(value, restored):
        return {"kind": "unrepresentable", "detail": "literal does not round-trip"}
    return {"kind": "return", "value": text, "type": type(value).__name__}


def _raise_line(exc, filename):
    line = None
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == filename:
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def _run_call(code_obj, function, args_src, kwargs_src, filename, budget, mode):
    namespace = {"__builtins__": builtins}
    hits = []
    if mode == "branches":

        def probe(index, value):
            result = bool(value)
            hits.append([index, result])
            return result

        namespace[PROBE] = probe
    exec(code_obj, namespace)  # trusted curation input only (see module docstring)
    func = namespace[function]
    args = _literal(args_src)
    kwargs = _literal(kwargs_src)
    lines = set()
    steps = [0]

    def local(frame, event, arg):
        if event == "line":
            steps[0] += 1
            if steps[0] > budget:
                raise _Budget()
            lines.add(frame.f_lineno)
        return local

    def global_trace(frame, event, arg):
        if frame.f_code.co_filename != filename:
            return None
        return local

    sys.settrace(global_trace)
    try:
        value = func(*args, **kwargs)
    except _Budget:
        outcome = {"kind": "timeout"}
    except (RecursionError, MemoryError) as exc:
        outcome = {"kind": "unstable", "detail": type(exc).__name__}
    except Exception as exc:  # the exception type is the observed behavior
        outcome = {
            "kind": "raise",
            "exception": type(exc).__name__,
            "line": _raise_line(exc, filename),
        }
    except BaseException as exc:  # e.g. SystemExit raised by the code
        outcome = {"kind": "unstable", "detail": type(exc).__name__}
    else:
        outcome = None
    finally:
        sys.settrace(None)
    if outcome is None:
        outcome = _return_outcome(value)
    if mode == "lines":
        outcome["lines"] = sorted(lines)
    if mode == "branches":
        outcome["branches"] = hits
    return outcome


def _run_job(job, budget):
    filename = "<curation:" + job["id"] + ">"
    try:
        code_obj = compile(job["code"], filename, "exec")
    except Exception as exc:  # reported to the parent
        return {"id": job["id"], "error": f"compile failed: {type(exc).__name__}: {exc}"}
    results = []
    for args_src, kwargs_src in job["calls"]:
        try:
            results.append(
                _run_call(
                    code_obj, job["function"], args_src, kwargs_src, filename, budget, job["mode"]
                )
            )
        except Exception as exc:  # harness-level failure for this call
            results.append({"kind": "harness_error", "detail": f"{type(exc).__name__}: {exc}"})
    return {"id": job["id"], "results": results}


def main():
    payload = json.loads(sys.stdin.read())
    budget = int(payload["line_budget"])
    output = [_run_job(job, budget) for job in payload["jobs"]]
    sys.stdout.write(json.dumps(output))


if __name__ == "__main__":
    main()

"""Reference tests for curated functions.

For each function the pipeline builds candidate calls, executes the trusted original in
the curation executor twice (hash seeds 0 and 1) with line tracing, once with branch
probes, and executes the reference target and single-point mutants on the same calls.
A call is usable when the original returns a literal-representable value or raises from
one of its own raise statements, with the same outcome under both hash seeds. The
target must reproduce every usable outcome (differential test), and the selected tests
must execute every return and raise statement of the original. Selection then prefers
calls that cover new branch outcomes and distinguish mutants.
"""

from __future__ import annotations

import ast
import random
from collections import Counter
from dataclasses import dataclass, field

from refactor_ai.contracts import ReferenceExpectation, ReferenceTest
from refactor_ai.data.executor import JobResult

PROBE = "_curation_branch_probe"
MIN_TESTS = 5
DIVERSE_TESTS = 8
MAX_TESTS = 12
USABLE_KINDS = ("return", "raise")


def literal_source(value: object) -> str:
    text = repr(value)
    if ast.literal_eval(text) != value:
        raise ValueError(f"not a round-trip literal: {text}")
    return text


def _same_literal(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def calls_from_params(params, rng_key: str, max_calls: int = 400) -> list[tuple[str, str]]:
    """Cartesian product of the parameter value pools, as (args, kwargs) literal sources.

    Parameters without defaults are passed positionally; a parameter with a default is
    omitted when the value equals the default and passed by keyword otherwise. Larger
    products are sampled deterministically.
    """
    pools = [tuple(p.values) for p in params]
    sizes = [len(pool) for pool in pools]
    total = 1
    for size in sizes:
        total *= size
    if total == 0:
        return []
    if total > max_calls:
        indices = sorted(random.Random(rng_key).sample(range(total), max_calls))
    else:
        indices = list(range(total))
    calls = []
    for index in indices:
        combo = []
        for size, pool in zip(reversed(sizes), reversed(pools), strict=True):
            index, position = divmod(index, size)
            combo.append(pool[position])
        combo.reverse()
        args: list = []
        kwargs: dict = {}
        for param, value in zip(params, combo, strict=True):
            if param.has_default and _same_literal(value, param.default):
                continue
            if param.kw_only or param.has_default:
                kwargs[param.name] = value
            else:
                args.append(value)
        calls.append((literal_source(args), literal_source(kwargs)))
    return list(dict.fromkeys(calls))


def _function(code: str) -> ast.FunctionDef:
    func = ast.parse(code).body[0]
    if not isinstance(func, ast.FunctionDef):
        raise ValueError("expected a function definition")
    return func


def exit_lines(code: str) -> set[int]:
    func = _function(code)
    return {node.lineno for node in ast.walk(func) if isinstance(node, (ast.Return, ast.Raise))}


def raise_lines(code: str) -> set[int]:
    func = _function(code)
    return {node.lineno for node in ast.walk(func) if isinstance(node, ast.Raise)}


def statement_lines(code: str) -> set[int]:
    func = _function(code)
    body = func.body
    if ast.get_docstring(func) is not None:
        body = body[1:]
    lines = set()
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.stmt):
                lines.add(node.lineno)
    return lines


class _Probe(ast.NodeTransformer):
    def __init__(self) -> None:
        self.count = 0

    def visit_If(self, node: ast.If) -> ast.If:
        self.generic_visit(node)
        node.test = ast.Call(
            func=ast.Name(id=PROBE, ctx=ast.Load()),
            args=[ast.Constant(self.count), node.test],
            keywords=[],
        )
        self.count += 1
        return node


def instrument_branches(code: str) -> tuple[str, int]:
    """Wrap every if-condition in a probe call that records its index and truth value.

    The probe evaluates the condition's truth value once and returns that bool, so the
    instrumented function behaves like the original. Only probe hits are read from this
    run; line numbers come from the uninstrumented run.
    """
    tree = ast.parse(code)
    probe = _Probe()
    tree = probe.visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n", probe.count


def outcome_key(outcome: dict) -> tuple:
    kind = outcome.get("kind")
    if kind == "return":
        return ("return", outcome["type"], outcome["value"])
    if kind == "raise":
        return ("raise", outcome["exception"])
    return (kind, outcome.get("detail"))


@dataclass
class TestPlan:
    tests: list[dict]
    selected: list[int]
    metrics: dict
    discarded: Counter = field(default_factory=Counter)


@dataclass
class Rejection:
    reason: str
    detail: str


def build_test_plan(
    code: str,
    calls: list[tuple[str, str]],
    seed0: JobResult,
    seed1: JobResult,
    branches: JobResult,
    target: JobResult,
    mutant_results: dict[str, JobResult],
    branch_count: int,
    *,
    preferred: set[int] | None = None,
    min_tests: int = MIN_TESTS,
    max_tests: int = MAX_TESTS,
    diverse_tests: int = DIVERSE_TESTS,
) -> TestPlan | Rejection:
    """Choose reference tests or explain why the function cannot get trustworthy tests.

    Order of preference: calls from the source's own tests, then (greedily) calls that
    execute uncovered return/raise lines, new branch outcomes, distinguish more mutants,
    or execute new statements; then calls with an outcome not yet represented, up to
    diverse_tests; then any usable calls up to min_tests.
    """
    for name, result in (("original", seed0), ("original_seed1", seed1), ("target", target)):
        if result.error or len(result.results) != len(calls):
            return Rejection(
                "execution_error", f"{name}: {result.error or 'result count mismatch'}"
            )
    if branches.error or len(branches.results) != len(calls):
        return Rejection(
            "execution_error", f"branches: {branches.error or 'result count mismatch'}"
        )
    explicit_raises = raise_lines(code)
    required = exit_lines(code)
    statements = statement_lines(code)
    discarded: Counter = Counter()
    usable: list[int] = []
    for index, (first, second) in enumerate(zip(seed0.results, seed1.results, strict=True)):
        kind = first.get("kind")
        if kind not in USABLE_KINDS:
            discarded[f"original_{kind}"] += 1
            continue
        if outcome_key(first) != outcome_key(second):
            discarded["hash_seed_dependent"] += 1
            continue
        if kind == "raise" and first.get("line") not in explicit_raises:
            discarded["incidental_exception"] += 1
            continue
        usable.append(index)
    if not usable:
        return Rejection(
            "no_usable_calls", f"all {len(calls)} candidate calls discarded: {dict(discarded)}"
        )
    mismatches = [
        index
        for index in usable
        if outcome_key(target.results[index]) != outcome_key(seed0.results[index])
    ]
    if mismatches:
        examples = "; ".join(
            f"{calls[i][0]} {calls[i][1]}: original {outcome_key(seed0.results[i])} "
            f"target {outcome_key(target.results[i])}"
            for i in mismatches[:3]
        )
        return Rejection("differential_mismatch", f"{len(mismatches)} calls differ: {examples}")

    live_mutants = {
        mutant_id: result
        for mutant_id, result in sorted(mutant_results.items())
        if not result.error and len(result.results) == len(calls)
    }
    lines_of = {i: set(seed0.results[i].get("lines", [])) for i in usable}
    branches_of = {
        i: {tuple(hit) for hit in branches.results[i].get("branches", [])} for i in usable
    }
    kills_of = {
        i: {
            mutant_id
            for mutant_id, result in live_mutants.items()
            if outcome_key(result.results[i]) != outcome_key(seed0.results[i])
        }
        for i in usable
    }
    reachable_required = set().union(*(lines_of[i] & required for i in usable))
    if reachable_required != required:
        missing = sorted(required - reachable_required)
        return Rejection("uncovered_exit_lines", f"return/raise lines never executed: {missing}")

    selected: list[int] = []
    covered: dict[str, set] = {"required": set(), "branches": set(), "kills": set(), "stmts": set()}

    def gains(i: int) -> tuple[int, int, int, int]:
        return (
            len((lines_of[i] & required) - covered["required"]),
            len(branches_of[i] - covered["branches"]),
            len(kills_of[i] - covered["kills"]),
            len((lines_of[i] & statements) - covered["stmts"]),
        )

    def take(i: int) -> None:
        selected.append(i)
        covered["required"] |= lines_of[i] & required
        covered["branches"] |= branches_of[i]
        covered["kills"] |= kills_of[i]
        covered["stmts"] |= lines_of[i] & statements

    for i in sorted(preferred or ()):
        if i in lines_of:
            take(i)
    while True:
        remaining = [i for i in usable if i not in selected]
        if not remaining:
            break
        best = max(remaining, key=lambda i: (gains(i), -i))
        best_gain = gains(best)
        if best_gain == (0, 0, 0, 0):
            break
        if len(selected) >= max_tests and best_gain[0] == 0:
            break
        take(best)
    # Outcome diversity: add calls whose outcome no selected test shows yet (for example a
    # capped value or another return expression), which coverage and condition mutants
    # alone do not reward.
    seen_keys = {outcome_key(seed0.results[i]) for i in selected}
    for i in usable:
        if len(selected) >= min(diverse_tests, max_tests):
            break
        key = outcome_key(seed0.results[i])
        if i not in selected and key not in seen_keys:
            take(i)
            seen_keys.add(key)
    if len(selected) < min_tests:
        rest = [i for i in usable if i not in selected]
        for i in rest[: min_tests - len(selected)]:
            take(i)
    selected.sort()

    tests = []
    for i in selected:
        outcome = seed0.results[i]
        if outcome["kind"] == "return":
            expect = ReferenceExpectation(kind="return", value=outcome["value"])
        else:
            expect = ReferenceExpectation(kind="raise", exception=outcome["exception"])
        tests.append(
            ReferenceTest(args=calls[i][0], kwargs=calls[i][1], expect=expect).model_dump(
                mode="json"
            )
        )
    killable = set().union(*(kills_of[i] for i in usable))
    killed = set().union(*(kills_of[i] for i in selected))
    reachable_branches = set().union(*(branches_of[i] for i in usable))
    metrics = {
        "candidate_calls": len(calls),
        "usable_calls": len(usable),
        "differential_calls_equal": len(usable),
        "tests": len(selected),
        "exit_lines": len(required),
        "exit_lines_covered": len(covered["required"]),
        "branch_outcomes_total": 2 * branch_count,
        "branch_outcomes_reachable": len(reachable_branches),
        "branch_outcomes_covered": len(covered["branches"]),
        "statement_lines": len(statements),
        "statement_lines_covered": len(covered["stmts"]),
        "mutants": len(live_mutants),
        "mutants_killable": len(killable),
        "mutants_killed": len(killed),
    }
    return TestPlan(tests=tests, selected=selected, metrics=metrics, discarded=discarded)

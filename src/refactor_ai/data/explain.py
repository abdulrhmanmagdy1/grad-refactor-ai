"""Deterministic explanations of the reference transformation for training targets.

The explanation lists the conditionals that guard_clauses.to_guard_clauses turned into
guard clauses, in the order they appear in the target, with what each guard does, and
states the measured nesting depth before and after. It follows the same traversal and
planning rules as the transformation, so it describes the actual change.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from refactor_ai.task_format import MAX_EXPLANATION_CHARS
from refactor_ai.tasks import guard_clauses

MAX_LISTED = 3
MAX_VALUE_CHARS = 40


@dataclass(frozen=True)
class GuardChange:
    condition: str
    action: str
    inverted: bool
    original_condition: str
    line: int


def _action(stmts: list[ast.stmt]) -> str:
    last = stmts[-1]
    if isinstance(last, ast.Raise):
        exc = last.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        if isinstance(exc, ast.Name):
            return f"raises {exc.id}"
        return "raises an exception"
    if isinstance(last, ast.Return):
        if last.value is None:
            return "returns None"
        text = ast.unparse(last.value)
        return f"returns {text}" if len(text) <= MAX_VALUE_CHARS else "returns early"
    return "returns or raises early"


def _collect(stmts: list[ast.stmt], out: list[GuardChange]) -> None:
    """Mirror of guard_clauses._transform_block, recording each guard it creates."""
    for stmt in stmts:
        if not isinstance(stmt, ast.If):
            continue
        plan = guard_clauses._plan(stmt)
        original = ast.unparse(stmt.test)
        if plan == "keep":
            out.append(GuardChange(original, _action(stmt.body), False, original, stmt.lineno))
            _collect(stmt.body, out)
            _collect(stmt.orelse, out)
        elif plan == "invert":
            negated = ast.unparse(guard_clauses.negate(stmt.test))
            out.append(GuardChange(negated, _action(stmt.orelse), True, original, stmt.lineno))
            _collect(stmt.orelse, out)
            _collect(stmt.body, out)
        else:
            _collect_children(stmt, out)


def _collect_children(node: ast.If, out: list[GuardChange]) -> None:
    """Mirror of guard_clauses._rewrite_children: elif chains stay flat and unplanned."""
    _collect(node.body, out)
    if guard_clauses._is_elif(node):
        _collect_children(node.orelse[0], out)
    else:
        _collect(node.orelse, out)


def guard_changes(code: str) -> list[GuardChange]:
    func, reason = guard_clauses.parse_function(code)
    if func is None:
        raise ValueError(f"not a single function: {reason}")
    changes: list[GuardChange] = []
    _collect(func.body, changes)
    return changes


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def explain(original: str, target: str) -> str:
    """One or two sentences describing the change from original to target."""
    changes = guard_changes(original)
    if not changes:
        raise ValueError("the transformation produced no guard clause")
    before = guard_clauses.code_nesting_depth(original)
    after = guard_clauses.code_nesting_depth(target)
    depth = f"reducing the maximum nesting depth from {before} to {after}."
    described = [f"`{change.condition}` {change.action}" for change in changes[:MAX_LISTED]]
    if len(changes) > MAX_LISTED:
        more = len(changes) - MAX_LISTED
        described.append(
            "1 more check exits early" if more == 1 else f"{more} more checks exit early"
        )
    if len(changes) == 1:
        text = (
            f"Turned the if/else into a guard clause: {described[0]} up front. "
            f"The remaining logic is dedented, {depth}"
        )
    else:
        text = (
            f"Turned {len(changes)} if/else conditionals into guard clauses: "
            f"{_join(described)}. The remaining logic is dedented, {depth}"
        )
    if len(text) > MAX_EXPLANATION_CHARS:
        text = (
            f"Turned {len(changes)} if/else conditionals into guard clauses that return or "
            f"raise early. The remaining logic is dedented, {depth}"
        )
    return text

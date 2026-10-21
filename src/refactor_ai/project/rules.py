"""Project rules that ruff's stable rules do not cover, checked on the syntax tree only.

- iterated-list-mutated: a `for` loop over a name whose body removes, inserts or appends
  items of that same list (items are skipped or the loop never ends).
- identity-comparison-of-computed-value: `is` or `is not` between values that are built at
  run time, such as a string made by concatenation, so the result depends on object
  identity rather than equality.
- value-never-used: a local variable that is only ever updated from itself (`x = x + 1`)
  and never read for anything else.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

MUTATING_METHODS = frozenset({"remove", "pop", "append", "insert", "extend", "clear"})
_IDENTITY_SAFE = (type(None), bool, type(Ellipsis))


@dataclass(frozen=True)
class RuleHit:
    rule: str
    line: int
    end_line: int
    message: str


def _functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _own_nodes(function: ast.AST):
    """Nodes of a function body, without descending into nested functions or classes."""
    stack = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def iterated_list_mutated(tree: ast.AST) -> list[RuleHit]:
    hits = []
    for loop in ast.walk(tree):
        if not isinstance(loop, (ast.For, ast.AsyncFor)) or not isinstance(loop.iter, ast.Name):
            continue
        name = loop.iter.id
        for node in (n for statement in loop.body for n in ast.walk(statement)):
            mutated = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in MUTATING_METHODS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == name
            ) or (
                isinstance(node, ast.Delete)
                and any(
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == name
                    for target in node.targets
                )
            )
            if mutated:
                hits.append(
                    RuleHit(
                        "iterated-list-mutated",
                        node.lineno,
                        node.end_lineno or node.lineno,
                        f"`{name}` is changed while the `for` loop at line {loop.lineno} iterates "
                        "over it, so items are skipped or the loop does not end.",
                    )
                )
                break
    return hits


def _built_at_run_time(value: ast.expr) -> bool:
    if isinstance(value, ast.JoinedStr):
        return True
    if isinstance(value, ast.BinOp) and isinstance(value.op, (ast.Add, ast.Mod, ast.Mult)):
        return any(
            isinstance(side, (ast.JoinedStr, ast.Constant))
            and isinstance(getattr(side, "value", ""), (str, bytes))
            or _built_at_run_time(side)
            for side in (value.left, value.right)
        )
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name) and func.id in ("str", "repr", "format", "int", "float"):
            return True
        if isinstance(func, ast.Attribute) and func.attr in (
            "format",
            "join",
            "lower",
            "upper",
            "strip",
            "replace",
        ):
            return True
    return False


def identity_comparison_of_computed_value(tree: ast.AST) -> list[RuleHit]:
    hits = []
    for function in _functions(tree):
        built: set[str] = set()
        for node in _own_nodes(function):
            if isinstance(node, ast.Assign) and _built_at_run_time(node.value):
                built.update(t.id for t in node.targets if isinstance(t, ast.Name))
        for node in _own_nodes(function):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            for op, left, right in zip(node.ops, operands, operands[1:], strict=False):
                if not isinstance(op, (ast.Is, ast.IsNot)):
                    continue
                sides = (left, right)
                if any(
                    isinstance(side, ast.Constant) and isinstance(side.value, _IDENTITY_SAFE)
                    for side in sides
                ):
                    continue
                if any(
                    _built_at_run_time(side) or (isinstance(side, ast.Name) and side.id in built)
                    for side in sides
                ):
                    hits.append(
                        RuleHit(
                            "identity-comparison-of-computed-value",
                            node.lineno,
                            node.end_lineno or node.lineno,
                            "`is` compares object identity, but one side is a value built at run "
                            "time; use `==` to compare the values.",
                        )
                    )
                    break
    return hits


def value_never_used(tree: ast.AST) -> list[RuleHit]:
    hits = []
    for function in _functions(tree):
        argument_names = {a.arg for a in ast.walk(function.args) if isinstance(a, ast.arg)}
        declared_elsewhere: set[str] = set()
        loads: dict[str, list[ast.Name]] = {}
        self_updates: dict[str, list[ast.stmt]] = {}
        # Reads in nested functions count too: a closure may use the value.
        for node in ast.walk(function):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loads.setdefault(node.id, []).append(node)
        for node in _own_nodes(function):
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                declared_elsewhere.update(node.names)
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                self_updates.setdefault(node.target.id, []).append(node)
            elif (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                name = node.targets[0].id
                if any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(node.value)):
                    self_updates.setdefault(name, []).append(node)
        for name, updates in self_updates.items():
            if name in argument_names or name in declared_elsewhere or name.startswith("_"):
                continue
            inside = {
                id(n)
                for update in updates
                for n in ast.walk(update.value)
                if isinstance(n, ast.Name) and n.id == name
            }
            other_loads = [n for n in loads.get(name, []) if id(n) not in inside]
            if not other_loads:
                first = updates[0]
                hits.append(
                    RuleHit(
                        "value-never-used",
                        first.lineno,
                        first.end_lineno or first.lineno,
                        f"`{name}` is only ever updated from itself and never read, so the "
                        "computation has no effect.",
                    )
                )
    return hits


RULES = (iterated_list_mutated, identity_comparison_of_computed_value, value_never_used)


def check(tree: ast.AST) -> list[RuleHit]:
    hits = [hit for rule in RULES for hit in rule(tree)]
    return sorted(hits, key=lambda hit: (hit.line, hit.rule))

"""Single-point mutants of an original function, used to choose stronger reference tests.

The mutants model mistakes a refactoring can introduce in guard conditions and exits:
an off-by-one comparison (< versus <=), a flipped equality or membership test, and
swapped with or, a dropped or added ``not``, an inverted branch, a guard whose return
or raise was lost, and a dropped clamp or conversion (``min(a, b)``, ``round(x, 2)``
or ``abs(x)`` reduced to its first argument). Test selection prefers inputs that
distinguish these mutants from the original. Mutants are executed only by the curation
executor.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

_COMPARE_SWAPS = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}


UNWRAPPED_CALLS = frozenset({"min", "max", "round", "abs", "int", "float"})


@dataclass(frozen=True)
class Mutant:
    mutant_id: str
    operator: str
    line: int
    code: str


def _condition_nodes(func: ast.AST) -> list[ast.AST]:
    """Conditions of if statements and conditional expressions, in walk order."""
    tests = []
    for node in ast.walk(func):
        if isinstance(node, (ast.If, ast.IfExp, ast.While)):
            tests.append(node.test)
    return tests


def _sites(func: ast.AST) -> list[tuple[str, ast.AST, int]]:
    sites: list[tuple[str, ast.AST, int]] = []
    for test in _condition_nodes(func):
        for node in ast.walk(test):
            if isinstance(node, ast.Compare):
                for index, op in enumerate(node.ops):
                    if type(op) in _COMPARE_SWAPS:
                        sites.append(("compare", node, index))
            elif isinstance(node, ast.BoolOp):
                sites.append(("boolop", node, 0))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                sites.append(("drop_not", node, 0))
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in UNWRAPPED_CALLS
            and node.args
            and not isinstance(node.args[0], ast.Starred)
        ):
            sites.append(("unwrap_call", node, 0))
    for node in ast.walk(func):
        if isinstance(node, ast.If):
            sites.append(("negate_if", node, 0))
            for branch_index, branch in enumerate((node.body, node.orelse)):
                if branch and isinstance(branch[-1], (ast.Return, ast.Raise)):
                    sites.append(("drop_exit", node, branch_index))
    return sites


class _Replace(ast.NodeTransformer):
    def __init__(self, target: ast.AST, replacement: ast.AST) -> None:
        self.target = target
        self.replacement = replacement

    def visit(self, node: ast.AST) -> ast.AST:
        if node is self.target:
            return self.replacement
        return super().visit(node)


def _apply(tree: ast.Module, kind: str, node: ast.AST, index: int) -> ast.Module:
    if kind == "compare":
        node.ops[index] = _COMPARE_SWAPS[type(node.ops[index])]()
    elif kind == "boolop":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif kind == "drop_not":
        tree = _Replace(node, node.operand).visit(tree)
    elif kind == "unwrap_call":
        tree = _Replace(node, node.args[0]).visit(tree)
    elif kind == "negate_if":
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif kind == "drop_exit":
        branch = node.body if index == 0 else node.orelse
        branch.pop()
        if not branch:
            branch.append(ast.Pass())
    return tree


def mutants(code: str, prefix: str = "m") -> list[Mutant]:
    """All distinct, syntactically valid single-point mutants, in a deterministic order."""
    tree = ast.parse(code)
    func = tree.body[0]
    original = ast.dump(tree)
    seen = {original}
    result: list[Mutant] = []
    for position, (kind, node, index) in enumerate(_sites(func)):
        clone = ast.parse(code)  # a fresh tree per mutant; cheaper than copy.deepcopy
        clone_kind, clone_node, clone_index = _sites(clone.body[0])[position]
        if clone_kind != kind or clone_index != index:
            raise AssertionError("mutation sites are not enumerated deterministically")
        mutated = _apply(clone, clone_kind, clone_node, clone_index)
        ast.fix_missing_locations(mutated)
        try:
            text = ast.unparse(mutated) + "\n"
            dumped = ast.dump(ast.parse(text))
        except (SyntaxError, ValueError):
            continue
        if dumped in seen:
            continue
        seen.add(dumped)
        result.append(
            Mutant(
                mutant_id=f"{prefix}{len(result)}",
                operator=kind,
                line=getattr(node, "lineno", 0),
                code=text,
            )
        )
    return result

"""Formatting helpers for team-authored functions.

Template originals are normalized with the same printer that produces reference targets
(ast.unparse), so an original and its target differ only by the refactoring. The stock
printer collapses ``else:`` followed by a nested ``if`` into ``elif``, which would remove
exactly the nesting the task is about, so a printer that keeps nesting as written is used
for originals. Comments are not part of template originals.
"""

from __future__ import annotations

import ast

from refactor_ai.tasks import guard_clauses


class _NestingPreservingUnparser(ast._Unparser):  # the printer behind ast.unparse (3.11)
    """ast.unparse, except that ``else: if`` stays nested unless it was written as elif."""

    def visit_If(self, node: ast.If) -> None:
        self.fill("if ")
        self.traverse(node.test)
        with self.block():
            self.traverse(node.body)
        while _written_as_elif(node):
            node = node.orelse[0]
            self.fill("elif ")
            self.traverse(node.test)
            with self.block():
                self.traverse(node.body)
        if node.orelse:
            self.fill("else")
            with self.block():
                self.traverse(node.orelse)


def _written_as_elif(node: ast.If) -> bool:
    if len(node.orelse) != 1 or not isinstance(node.orelse[0], ast.If):
        return False
    return getattr(node.orelse[0], "col_offset", None) == getattr(node, "col_offset", None)


def canonical_function(code: str) -> str:
    """Normalize formatting while keeping else/if nesting; raises SyntaxError if invalid."""
    tree = ast.parse(code)
    text = _NestingPreservingUnparser().visit(tree) + "\n"
    if ast.dump(ast.parse(text)) != ast.dump(tree):
        raise ValueError("canonical formatting changed the syntax tree")
    if guard_clauses.code_nesting_depth(text) != guard_clauses.code_nesting_depth(code):
        raise ValueError("canonical formatting changed the nesting depth")
    return text


def indent(lines: list[str] | tuple[str, ...], levels: int = 1) -> list[str]:
    pad = "    " * levels
    return [pad + line if line else line for line in lines]


def literal(value: object) -> str:
    """Deterministic Python literal source for a template constant (no sets)."""
    if isinstance(value, (set, frozenset)):
        raise TypeError("set literals have hash-dependent order; use a tuple")
    if isinstance(value, float) and value != value:  # NaN is out of the task scope
        raise ValueError("NaN constants are out of scope")
    text = repr(value)
    if ast.literal_eval(text) != value:
        raise ValueError(f"value is not a round-trip literal: {text}")
    return text

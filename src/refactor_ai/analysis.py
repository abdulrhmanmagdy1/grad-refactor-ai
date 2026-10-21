"""Static heuristics only. Never execute submitted code."""

import ast

from pydantic import BaseModel


class Finding(BaseModel):
    rule: str
    line: int
    message: str


class AnalysisResult(BaseModel):
    syntax_valid: bool
    findings: list[Finding]
    error: str | None = None
    engine: str = "static-heuristics"


BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)


def _elif_of(node: ast.AST) -> ast.If | None:
    """The elif that continues an if statement (an if alone in else, same column)."""
    if (
        isinstance(node, ast.If)
        and len(node.orelse) == 1
        and isinstance(node.orelse[0], ast.If)
        and node.orelse[0].col_offset == node.col_offset
    ):
        return node.orelse[0]
    return None


def analyze(code: str) -> AnalysisResult:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return AnalysisResult(syntax_valid=False, findings=[], error=str(exc))
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            if length > 30:
                findings.append(
                    Finding(
                        rule="long-function",
                        line=node.lineno,
                        message=(
                            f"Function {node.name} spans {length} lines; "
                            "review its responsibilities."
                        ),
                    )
                )

    def visit(node: ast.AST, depth: int = 0, continues_chain: bool = False) -> None:
        # Function and class bodies establish a new nesting context.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            depth = 0
        current = depth + int(isinstance(node, BLOCKS))
        if isinstance(node, BLOCKS) and current == 4 and not continues_chain:
            findings.append(
                Finding(
                    rule="deep-nesting",
                    line=node.lineno,
                    message="Four nested control blocks; consider simplifying control flow.",
                )
            )
        elif_node = _elif_of(node)
        for child in ast.iter_child_nodes(node):
            if child is elif_node:
                # An elif continues its if at the same level instead of nesting deeper.
                visit(child, depth, continues_chain=True)
            else:
                visit(child, current)

    try:
        visit(tree)
    except RecursionError:
        return AnalysisResult(syntax_valid=False, findings=[], error="Code nesting exceeds limits.")
    return AnalysisResult(syntax_valid=True, findings=findings)

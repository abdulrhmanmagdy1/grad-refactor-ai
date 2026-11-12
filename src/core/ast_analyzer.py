"""Deep Software Engineering AST & Metrics Engine (FR02, NFR01).

Parses code safely with ast.parse (never executing it) and detects code smells,
anti-patterns, and engineering metrics:

Structural detectors
    - long-function (>30 lines, sync & async)
    - high-complexity (McCabe Cyclomatic Complexity > 10)
    - deep-nesting (control-structure nesting > 3 levels)
    - high-cognitive-complexity (SonarSource-style weighted complexity)
    - long-parameter-list (functions taking > 5 parameters)
    - mutable-default-arg (list/dict/set literal or constructor defaults)
    - broad-exception-catch (bare except / Exception without re-raise or logging)
    - dead-code-or-unused (unreachable statements and unused local assignments)
    - duplicate-code-blocks (exact normalized AST subtree clones)

Quantitative metrics
    - Halstead vocabulary, length, volume, difficulty, effort, estimated bugs
    - Maintainability Index (0-100) from Halstead volume, complexity, and LOC
    - Per-function metric records and an AST constellation graph for the 3D UI
"""

import ast
import math
from collections import Counter
from typing import Any

from core.exceptions import InvalidSyntaxError
from core.schemas import AnalysisResult, ASTFinding, ASTGraph, ASTGraphEdge, ASTGraphNode

CONTROL_BLOCKS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)

GRAPH_NODE_TYPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)

_FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)

BROAD_EXCEPTION_NAMES = {"Exception", "BaseException"}

_LOGGING_METHODS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "log",
}

_MUTABLE_LITERALS = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
_MUTABLE_CALL_NAMES = {"list", "dict", "set", "bytearray"}

_TERMINATORS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


def calculate_cyclomatic_complexity(node: ast.AST) -> int:
    """Calculate McCabe Cyclomatic Complexity for a function or code block.

    Base complexity is 1. Adds 1 for each decision point/branch.
    """
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.IfExp)):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # 'a and b and c' has 2 decision points
            complexity += max(0, len(child.values) - 1)
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for generator in child.generators:
                complexity += len(generator.ifs)
    return complexity


def calculate_cognitive_complexity(node: ast.AST) -> int:
    """Calculate a SonarSource-style Cognitive Complexity score.

    Structural increments are weighted by nesting depth, boolean operator
    sequences and recursion add flat increments, and nested function scopes
    are scored independently (they are visited by their own FunctionDef).
    """
    score = 0

    def walk_expression(expr: ast.AST) -> None:
        nonlocal score
        if isinstance(expr, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return
        if isinstance(expr, ast.BoolOp):
            # One increment per boolean operator sequence, regardless of length.
            score += 1
        elif isinstance(expr, ast.IfExp):
            score += 1
        for child in ast.iter_child_nodes(expr):
            if not isinstance(child, ast.stmt):
                walk_expression(child)

    def walk_statements(stmts: list[ast.stmt], nesting: int) -> None:
        nonlocal score
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                score += 1 + nesting
                walk_expression(stmt.test)
                walk_statements(stmt.body, nesting + 1)
                if stmt.orelse:
                    if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                        # 'elif' continues the chain without a nesting penalty.
                        walk_statements(stmt.orelse, nesting)
                    else:
                        score += 1
                        walk_statements(stmt.orelse, nesting + 1)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                score += 1 + nesting
                walk_expression(stmt.iter)
                walk_statements(stmt.body, nesting + 1)
                walk_statements(stmt.orelse, nesting + 1)
            elif isinstance(stmt, ast.While):
                score += 1 + nesting
                walk_expression(stmt.test)
                walk_statements(stmt.body, nesting + 1)
                walk_statements(stmt.orelse, nesting + 1)
            elif isinstance(stmt, _SCOPE_TYPES):
                # Nested scopes are scored by their own analyzer pass.
                continue
            elif isinstance(stmt, ast.Try):
                walk_statements(stmt.body, nesting)
                for handler in stmt.handlers:
                    score += 1 + nesting
                    walk_statements(handler.body, nesting + 1)
                walk_statements(stmt.orelse, nesting)
                walk_statements(stmt.finalbody, nesting)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                walk_statements(stmt.body, nesting)
            elif isinstance(stmt, (ast.Break, ast.Continue)):
                score += 1
            elif isinstance(stmt, ast.Match):
                score += 1 + nesting
                for case in stmt.cases:
                    walk_statements(case.body, nesting + 1)
            else:
                for child in ast.iter_child_nodes(stmt):
                    if not isinstance(child, ast.stmt):
                        walk_expression(child)

    if isinstance(node, ast.Module):
        walk_statements(node.body, 0)
    elif isinstance(node, _FUNCTION_TYPES):
        walk_statements(node.body, 0)
        if _is_recursive(node):
            score += 1
    else:
        walk_statements(list(ast.iter_child_nodes(node)), 0)
    return score


def _is_recursive(func: ast.AST) -> bool:
    """Detect a direct recursive call owned by this function scope."""
    if not isinstance(func, _FUNCTION_TYPES):
        return False
    for child in ast.iter_child_nodes(func):
        stack = [child]
        while stack:
            current = stack.pop()
            if isinstance(current, _SCOPE_TYPES) and current is not func:
                continue
            if (
                isinstance(current, ast.Call)
                and isinstance(current.func, ast.Name)
                and current.func.id == func.name
            ):
                return True
            stack.extend(ast.iter_child_nodes(current))
    return False


def calculate_halstead(tree: ast.AST) -> dict[str, float]:
    """Calculate Halstead software-science metrics over a parsed AST.

    Operators: arithmetic/bitwise/comparison/boolean/unary operators,
    augmented assignments, def/class/return/yield constructs.
    Operands: identifiers, attributes, constants, and parameters.
    """
    operators: Counter[str] = Counter()
    operands: Counter[tuple[str, str]] = Counter()

    for node in ast.walk(tree):
        if isinstance(node, (ast.operator, ast.boolop, ast.unaryop, ast.cmpop)):
            operators[type(node).__name__] += 1
        elif isinstance(node, ast.AugAssign):
            operators[f"{type(node.op).__name__}="] += 1
        elif isinstance(node, _FUNCTION_TYPES):
            operators["def"] += 1
            operands[("name", node.name)] += 1
        elif isinstance(node, ast.ClassDef):
            operators["class"] += 1
            operands[("name", node.name)] += 1
        elif isinstance(node, ast.Name):
            operands[("name", node.id)] += 1
        elif isinstance(node, ast.Attribute):
            operands[("attr", node.attr)] += 1
        elif isinstance(node, ast.Constant):
            operands[("const", repr(node.value))] += 1
        elif isinstance(node, ast.arg):
            operands[("param", node.arg)] += 1
        elif isinstance(node, ast.Return):
            operators["return"] += 1
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            operators["yield"] += 1

    n1 = len(operators)
    n2 = len(operands)
    total_operators = sum(operators.values())
    total_operands = sum(operands.values())
    vocabulary = n1 + n2
    length = total_operators + total_operands
    volume = length * math.log2(vocabulary) if vocabulary > 0 else 0.0
    difficulty = (n1 / 2) * (total_operands / n2) if n2 > 0 else 0.0
    effort = difficulty * volume
    return {
        "distinct_operators": n1,
        "distinct_operands": n2,
        "total_operators": total_operators,
        "total_operands": total_operands,
        "vocabulary": vocabulary,
        "length": length,
        "volume": round(volume, 2),
        "difficulty": round(difficulty, 2),
        "effort": round(effort, 2),
        "estimated_bugs": round(volume / 3000.0, 4),
    }


def calculate_maintainability_index(
    halstead_volume: float,
    cyclomatic_complexity: int,
    loc: int,
) -> float:
    """Compute the normalized Maintainability Index in the 0-100 range.

    MI = max(0, (171 - 5.2*ln(V) - 0.23*CC - 16.2*ln(LOC)) * 100 / 171)
    Higher values indicate more maintainable code.
    """
    safe_loc = max(1, loc)
    safe_volume = max(halstead_volume, 1.0)
    raw = (
        (
            171
            - 5.2 * math.log(safe_volume)
            - 0.23 * cyclomatic_complexity
            - 16.2 * math.log(safe_loc)
        )
        * 100
        / 171
    )
    return round(min(100.0, max(0.0, raw)), 2)


def _iter_function_defaults(node: ast.AST) -> list[tuple[str, ast.AST]]:
    """Pair each parameter name with its default expression (positional + kwonly)."""
    if not isinstance(node, _FUNCTION_TYPES):
        return []
    positional = list(node.args.posonlyargs) + list(node.args.args)
    defaults = node.args.defaults
    offset = len(positional) - len(defaults)
    pairs: list[tuple[str, ast.AST]] = []
    for index, default in enumerate(defaults):
        pairs.append((positional[offset + index].arg, default))
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False):
        if default is not None:
            pairs.append((arg.arg, default))
    return pairs


def _is_mutable_default(node: ast.AST) -> bool:
    if isinstance(node, _MUTABLE_LITERALS):
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _MUTABLE_CALL_NAMES
        and not node.args
        and not node.keywords
    ):
        return True
    return False


def _count_parameters(node: ast.AST) -> int:
    if not isinstance(node, _FUNCTION_TYPES):
        return 0
    count = len(node.args.posonlyargs) + len(node.args.args) + len(node.args.kwonlyargs)
    if node.args.vararg:
        count += 1
    if node.args.kwarg:
        count += 1
    return count


def _iter_statement_lists(tree: ast.AST) -> list[list[ast.stmt]]:
    """Collect every statement list in the tree (bodies, handlers, clauses)."""
    lists: list[list[ast.stmt]] = []
    for node in ast.walk(tree):
        for attribute in ("body", "orelse", "finalbody"):
            value = getattr(node, attribute, None)
            if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
                lists.append(value)
    return lists


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    targets = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(
        isinstance(target, ast.Name) and target.id in BROAD_EXCEPTION_NAMES for target in targets
    )


def _handler_reraises_or_logs(handler: ast.ExceptHandler) -> bool:
    for child in ast.walk(handler):
        if isinstance(child, ast.Raise):
            return True
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            else:
                name = ""
            if name.lower() in _LOGGING_METHODS:
                return True
    return False


def _collect_assigned_names(target: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            names.extend(_collect_assigned_names(element))
    elif isinstance(target, ast.Starred):
        names.extend(_collect_assigned_names(target.value))
    return names


def _iter_scope_statements(node: ast.AST) -> list[ast.stmt]:
    """Yield statements of the current scope only (nested scopes excluded)."""
    collected: list[ast.stmt] = []

    def visit(current: ast.AST) -> None:
        for child in ast.iter_child_nodes(current):
            if isinstance(child, ast.stmt):
                collected.append(child)
                if isinstance(child, _SCOPE_TYPES):
                    continue
            if isinstance(child, (ast.Lambda,)):
                continue
            visit(child)

    visit(node)
    return collected


def _is_descendant(ancestor: ast.stmt, node: ast.stmt) -> bool:
    if ancestor is node:
        return False
    if not hasattr(ancestor, "end_lineno") or ancestor.end_lineno is None:
        return False
    return ancestor.lineno <= node.lineno and node.end_lineno <= ancestor.end_lineno


def extract_ast_graph(code: str, findings: list[ASTFinding] | None = None) -> ASTGraph:
    """Export a serializable AST constellation graph for the 3D spatial UI.

    Nodes represent the module, functions, async functions, classes, and
    nested control blocks; edges represent structural containment. Nodes
    flagged by the deterministic detectors are marked as smell hotspots.
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return ASTGraph()

    findings = findings or []
    smell_by_line: dict[int, str] = {}
    for finding in findings:
        smell_by_line.setdefault(finding.line, finding.rule)

    nodes: list[ASTGraphNode] = [
        ASTGraphNode(
            id="module",
            label="<module>",
            type="module",
            line=1,
            complexity=calculate_cyclomatic_complexity(tree),
        )
    ]
    edges: list[ASTGraphEdge] = []
    counter = 0

    def visit(parent: ast.AST, parent_id: str) -> None:
        nonlocal counter
        for child in ast.iter_child_nodes(parent):
            if not isinstance(child, GRAPH_NODE_TYPES):
                continue
            counter += 1
            node_id = f"n{counter}"
            if isinstance(child, ast.FunctionDef):
                type_name = "function"
                label = child.name
            elif isinstance(child, ast.AsyncFunctionDef):
                type_name = "async_function"
                label = child.name
            elif isinstance(child, ast.ClassDef):
                type_name = "class"
                label = child.name
            else:
                type_name = type(child).__name__.lower()
                label = f"{type_name}@{child.lineno}"
            smell = smell_by_line.get(child.lineno)
            nodes.append(
                ASTGraphNode(
                    id=node_id,
                    label=label,
                    type=type_name,
                    line=child.lineno,
                    complexity=calculate_cyclomatic_complexity(child),
                    has_smell=smell is not None,
                    smell_type=smell,
                )
            )
            edges.append(ASTGraphEdge(source=parent_id, target=node_id))
            visit(child, node_id)

    visit(tree, "module")
    return ASTGraph(nodes=nodes, edges=edges)


class ASTAnalyzer:
    """Safe AST analyzer enforcing deterministic structural checks and metrics."""

    def __init__(
        self,
        max_function_lines: int = 30,
        max_nesting_depth: int = 3,
        complexity_threshold: int = 10,
        cognitive_threshold: int = 15,
        max_parameters: int = 5,
        duplicate_min_nodes: int = 8,
    ) -> None:
        self.max_function_lines = max_function_lines
        self.max_nesting_depth = max_nesting_depth
        self.complexity_threshold = complexity_threshold
        self.cognitive_threshold = cognitive_threshold
        self.max_parameters = max_parameters
        self.duplicate_min_nodes = duplicate_min_nodes

    def parse_safely(self, code: str) -> ast.AST:
        """Parse Python source into AST. Rejects invalid syntax with descriptive error."""
        try:
            return ast.parse(code)
        except SyntaxError as exc:
            raise InvalidSyntaxError(
                message=f"SyntaxError: {exc.msg} at line {exc.lineno}:{exc.offset}",
                line=exc.lineno,
                offset=exc.offset,
            ) from exc
        except (ValueError, RecursionError) as exc:
            raise InvalidSyntaxError(message=f"AST parsing failure: {exc}") from exc

    def analyze(self, code: str) -> AnalysisResult:
        """Analyze code structure for code smells, anti-patterns, and metrics."""
        try:
            tree = self.parse_safely(code)
        except InvalidSyntaxError as exc:
            return AnalysisResult(
                syntax_valid=False,
                findings=[],
                error=exc.message,
                metrics={"loc": len(code.splitlines())},
                ast_graph=None,
            )

        findings: list[ASTFinding] = []
        functions_count = 0
        async_functions_count = 0
        classes_count = 0
        total_complexity = 0
        functions_meta: list[dict[str, Any]] = []

        # Per-function structural detectors (ordered: length, complexity, ...).
        for node in ast.walk(tree):
            if isinstance(node, _FUNCTION_TYPES):
                if isinstance(node, ast.AsyncFunctionDef):
                    async_functions_count += 1
                else:
                    functions_count += 1

                length = (node.end_lineno or node.lineno) - node.lineno + 1
                node_type = type(node).__name__
                is_async = isinstance(node, ast.AsyncFunctionDef)

                # Rule 1: Long function (> 30 lines)
                if length > self.max_function_lines:
                    findings.append(
                        ASTFinding(
                            rule="long-function",
                            line=node.lineno,
                            end_line=node.end_lineno,
                            node_type=node_type,
                            message=(
                                f"Function '{node.name}' spans {length} lines; "
                                "review its responsibilities."
                            ),
                            rationale=(
                                "Long functions violate the Single Responsibility Principle "
                                "and increase maintenance burden."
                            ),
                        )
                    )

                # Rule 2: High cyclomatic complexity
                comp = calculate_cyclomatic_complexity(node)
                total_complexity += comp
                if comp > self.complexity_threshold:
                    findings.append(
                        ASTFinding(
                            rule="high-complexity",
                            line=node.lineno,
                            end_line=node.end_lineno,
                            node_type=node_type,
                            message=(
                                f"Function '{node.name}' has cyclomatic complexity of {comp} "
                                f"(threshold: {self.complexity_threshold})."
                            ),
                            rationale=(
                                "High cyclomatic complexity indicates multiple branching paths, "
                                "making testing and reasoning difficult."
                            ),
                        )
                    )

                # Rule 4: High cognitive complexity (weighted nesting & reasoning load)
                cognitive = calculate_cognitive_complexity(node)
                if cognitive > self.cognitive_threshold:
                    findings.append(
                        ASTFinding(
                            rule="high-cognitive-complexity",
                            line=node.lineno,
                            end_line=node.end_lineno,
                            node_type=node_type,
                            message=(
                                f"Function '{node.name}' has cognitive complexity of {cognitive} "
                                f"(threshold: {self.cognitive_threshold})."
                            ),
                            rationale=(
                                "Cognitive complexity weights nesting depth, boolean chains, "
                                "and recursion, reflecting how hard the logic is to reason about."
                            ),
                        )
                    )

                # Rule 5: Long parameter list
                parameter_count = _count_parameters(node)
                if parameter_count > self.max_parameters:
                    findings.append(
                        ASTFinding(
                            rule="long-parameter-list",
                            line=node.lineno,
                            end_line=node.end_lineno,
                            node_type=node_type,
                            message=(
                                f"Function '{node.name}' takes {parameter_count} parameters "
                                f"(threshold: {self.max_parameters}); consider a parameter object."
                            ),
                            rationale=(
                                "Long parameter lists hinder readability, testing, and evolve "
                                "into shotgun surgery whenever a new argument is added."
                            ),
                        )
                    )

                # Rule 6: Mutable default arguments
                mutable_defaults = [
                    name
                    for name, default in _iter_function_defaults(node)
                    if _is_mutable_default(default)
                ]
                if mutable_defaults:
                    findings.append(
                        ASTFinding(
                            rule="mutable-default-arg",
                            line=node.lineno,
                            end_line=node.end_lineno,
                            node_type=node_type,
                            message=(
                                f"Function '{node.name}' uses mutable default argument(s): "
                                f"{', '.join(mutable_defaults)}."
                            ),
                            rationale=(
                                "Mutable defaults are shared across every call, causing state to "
                                "leak between invocations; use None and re-initialize inside."
                            ),
                        )
                    )

                # Rule 8a: Unused local assignments within this function scope
                findings.extend(self._unused_assignment_findings(node))

                # Per-function metric record
                function_halstead = calculate_halstead(node)
                functions_meta.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": node.end_lineno,
                        "lines": length,
                        "cyclomatic": comp,
                        "cognitive": cognitive,
                        "parameters": parameter_count,
                        "is_async": is_async,
                        "halstead_volume": function_halstead["volume"],
                        "maintainability_index": calculate_maintainability_index(
                            function_halstead["volume"], comp, length
                        ),
                    }
                )

            elif isinstance(node, ast.ClassDef):
                classes_count += 1

        # Rule 3: Deeply nested control blocks (> 3 levels, i.e. current == 4)
        def visit_nesting(node: ast.AST, depth: int = 0) -> None:
            if isinstance(node, (*_FUNCTION_TYPES, ast.ClassDef)):
                depth = 0

            is_control = isinstance(node, CONTROL_BLOCKS)
            current = depth + (1 if is_control else 0)

            if is_control and current > self.max_nesting_depth:
                findings.append(
                    ASTFinding(
                        rule="deep-nesting",
                        line=node.lineno,
                        end_line=getattr(node, "end_lineno", None),
                        node_type=type(node).__name__,
                        message=(
                            f"{current} nested control blocks; consider simplifying control flow."
                        ),
                        rationale=(
                            "Deep nesting obscures program logic, increases indentation, "
                            "and creates arrow anti-patterns."
                        ),
                    )
                )

            for child in ast.iter_child_nodes(node):
                visit_nesting(child, current)

        try:
            visit_nesting(tree)
        except RecursionError:
            return AnalysisResult(
                syntax_valid=False,
                findings=[],
                error="Code nesting exceeds system recursion limits.",
                metrics={"loc": len(code.splitlines())},
                ast_graph=None,
            )

        # Rule 7: Broad exception handlers without re-raise or logging
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
                if not _handler_reraises_or_logs(node):
                    findings.append(
                        ASTFinding(
                            rule="broad-exception-catch",
                            line=node.lineno,
                            end_line=getattr(node, "end_lineno", None),
                            node_type="ExceptHandler",
                            message=(
                                "Broad exception handler swallows errors without re-raising "
                                "or logging."
                            ),
                            rationale=(
                                "Catching Exception (or using a bare except) hides "
                                "programming errors and makes failures silent; catch "
                                "specific exceptions or log them."
                            ),
                        )
                    )

        # Rule 8b: Unreachable statements after return/raise/break/continue
        for stmts in _iter_statement_lists(tree):
            for index, stmt in enumerate(stmts):
                if isinstance(stmt, _TERMINATORS) and index + 1 < len(stmts):
                    dead = stmts[index + 1]
                    findings.append(
                        ASTFinding(
                            rule="dead-code-or-unused",
                            line=dead.lineno,
                            end_line=getattr(dead, "end_lineno", None),
                            node_type=type(dead).__name__,
                            message=(
                                f"Unreachable statement after "
                                f"'{type(stmt).__name__.lower()}' at line {stmt.lineno}."
                            ),
                            rationale=(
                                "Statements after an unconditional return/raise/break/continue "
                                "never execute and mislead readers and coverage tools."
                            ),
                        )
                    )
                    break

        # Rule 9: Duplicate code blocks (exact normalized subtree clones)
        findings.extend(self._duplicate_block_findings(tree))

        loc = len(
            [
                line
                for line in code.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        )
        halstead = calculate_halstead(tree)
        cognitive_total = calculate_cognitive_complexity(tree) + sum(
            meta["cognitive"] for meta in functions_meta
        )
        max_cognitive = max((meta["cognitive"] for meta in functions_meta), default=0)
        max_cyclomatic = max((meta["cyclomatic"] for meta in functions_meta), default=0)
        maintainability_index = calculate_maintainability_index(
            halstead["volume"], total_complexity, loc
        )

        metrics: dict[str, Any] = {
            "loc": loc,
            "raw_loc": len(code.splitlines()),
            "functions_count": functions_count,
            "async_functions_count": async_functions_count,
            "classes_count": classes_count,
            "total_cyclomatic_complexity": total_complexity,
            "max_cyclomatic_complexity": max_cyclomatic,
            "cognitive_complexity_total": cognitive_total,
            "max_cognitive_complexity": max_cognitive,
            "maintainability_index": maintainability_index,
            "halstead": halstead,
            "functions": functions_meta,
        }

        return AnalysisResult(
            syntax_valid=True,
            findings=findings,
            metrics=metrics,
            ast_graph=extract_ast_graph(code, findings),
        )

    def _unused_assignment_findings(self, func: ast.AST) -> list[ASTFinding]:
        """Detect local variables assigned but never read within a function scope."""
        loaded = {
            node.id
            for node in ast.walk(func)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        declared: set[str] = set()
        for node in ast.walk(func):
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                declared.update(node.names)

        findings: list[ASTFinding] = []
        reported: set[str] = set()
        for stmt in _iter_scope_statements(func):
            targets: list[tuple[str, int]] = []
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    targets.extend((name, stmt.lineno) for name in _collect_assigned_names(target))
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                targets.extend((name, stmt.lineno) for name in _collect_assigned_names(stmt.target))
            for name, line in targets:
                if name in loaded or name in declared or name in reported or name.startswith("_"):
                    continue
                reported.add(name)
                findings.append(
                    ASTFinding(
                        rule="dead-code-or-unused",
                        line=line,
                        end_line=line,
                        node_type="Assign",
                        message=(
                            f"Local variable '{name}' is assigned at line {line} but never read."
                        ),
                        rationale=(
                            "Unused local assignments add noise, suggest incomplete logic, "
                            "and are flagged by static analysis tools (F841)."
                        ),
                    )
                )
        return findings

    def _duplicate_block_findings(self, tree: ast.AST) -> list[ASTFinding]:
        """Detect exact duplicate statement subtrees via normalized AST fingerprints."""
        groups: dict[str, list[ast.stmt]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.stmt):
                continue
            if sum(1 for _ in ast.walk(node)) < self.duplicate_min_nodes:
                continue
            fingerprint = ast.dump(node, include_attributes=False)
            groups.setdefault(fingerprint, []).append(node)

        findings: list[ASTFinding] = []
        for nodes in groups.values():
            if len(nodes) < 2:
                continue
            ordered = sorted(nodes, key=lambda item: item.lineno)
            distinct: list[ast.stmt] = []
            for node in ordered:
                if any(_is_descendant(other, node) for other in distinct):
                    continue
                distinct.append(node)
            if len(distinct) < 2:
                continue
            lines = [node.lineno for node in distinct]
            findings.append(
                ASTFinding(
                    rule="duplicate-code-blocks",
                    line=lines[1],
                    end_line=distinct[1].end_lineno,
                    node_type=type(distinct[1]).__name__,
                    message=(
                        f"Duplicate code block repeated {len(distinct)} times at lines "
                        f"{lines}; extract a shared helper."
                    ),
                    rationale=(
                        "Duplicated logic must be changed in multiple places, causing "
                        "inconsistencies and increasing defect risk."
                    ),
                )
            )
        return findings


def analyze(code: str) -> AnalysisResult:
    """Global convenience function for AST analysis."""
    return ASTAnalyzer().analyze(code)

"""The supported refactoring: replace nested conditionals with guard clauses.

This module is the single definition of the task shared by the service, data curation,
training and evaluation. It is standard-library only so the separate training
environment can import it. It inspects and rewrites syntax trees; it never executes code.

Scope (task version 1): one synchronous, undecorated, top-level function without
imports, nested definitions, global/nonlocal, generators, try/with/match blocks, or
calls to input/output and dynamic-execution builtins. A case is supported when turning
conditionals whose branch always returns or raises into guard clauses lowers the
function's maximum control-block nesting depth.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

TASK_TYPE = "guard_clauses"
TASK_VERSION = 1
MAX_INPUT_CHARS = 3000
MAX_INPUT_LINES = 60
FINDING_TYPE = "nested_conditional"

DENIED_CALLS = frozenset(
    {
        "open",
        "print",
        "input",
        "exec",
        "eval",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "setattr",
        "delattr",
        "breakpoint",
        "exit",
        "quit",
        "help",
    }
)
BLOCK_TYPES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)
_EXACT_NEGATIONS = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}
# Inverting an ordering comparison is exact only for totally ordered operands, so it is
# applied only when one side is a numeric literal (NaN is documented as out of scope).
_ORDER_NEGATIONS = {ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt}

REASON_TEXT = {
    "syntax_error": "The input is not valid Python.",
    "too_long": f"The input exceeds {MAX_INPUT_CHARS} characters or {MAX_INPUT_LINES} lines.",
    "not_single_function": "The input must contain exactly one top-level function only.",
    "async_function": "Async functions are outside the supported scope.",
    "decorated_function": "Decorated functions are outside the supported scope.",
    "generator_function": "Generator functions are outside the supported scope.",
    "nested_definition": "Nested functions or classes are outside the supported scope.",
    "imports_present": "Imports are outside the supported scope.",
    "global_or_nonlocal": "global and nonlocal statements are outside the supported scope.",
    "try_or_with_present": "try and with blocks are outside the supported scope.",
    "match_present": "match statements are outside the supported scope.",
    "dunder_access": "Access to double-underscore names is outside the supported scope.",
    "no_opportunity": "No nested conditional can be flattened with guard clauses.",
    "too_complex": "The input is nested too deeply to analyze.",
}


@dataclass(frozen=True)
class Opportunity:
    start_line: int
    end_line: int
    reason: str


@dataclass
class InputCheck:
    supported: bool
    reasons: list[str] = field(default_factory=list)
    function_name: str | None = None
    nesting_depth: int | None = None
    opportunities: list[Opportunity] = field(default_factory=list)

    def describe(self) -> str:
        return " ".join(reason_text(code) for code in self.reasons)


@dataclass
class RubricResult:
    passed: bool
    checks: dict[str, bool]
    reasons: list[str]


def reason_text(code: str) -> str:
    if code.startswith("denied_call:"):
        return f"Calls to {code.split(':', 1)[1]}() are outside the supported scope."
    return REASON_TEXT.get(code, code)


def parse_function(code: str) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef | None, str | None]:
    """Return the single top-level function, or None and a reason code."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None, "syntax_error"
    if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None, "not_single_function"
    return tree.body[0], None


def constraint_violations(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    reasons: list[str] = []
    if isinstance(func, ast.AsyncFunctionDef):
        reasons.append("async_function")
    if func.decorator_list:
        reasons.append("decorated_function")
    for node in ast.walk(func):
        if node is not func and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            reasons.append("nested_definition")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            reasons.append("imports_present")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            reasons.append("global_or_nonlocal")
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            reasons.append("generator_function")
        elif isinstance(node, ast.Await):
            reasons.append("async_function")
        elif isinstance(node, (ast.Try, ast.TryStar, ast.With, ast.AsyncWith)):
            reasons.append("try_or_with_present")
        elif isinstance(node, ast.Match):
            reasons.append("match_present")
        elif isinstance(node, ast.Attribute) and _is_dunder(node.attr):
            reasons.append("dunder_access")
        elif isinstance(node, ast.Name) and _is_dunder(node.id):
            reasons.append("dunder_access")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in DENIED_CALLS
        ):
            reasons.append(f"denied_call:{node.func.id}")
    return list(dict.fromkeys(reasons))


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _is_elif(node: ast.If) -> bool:
    """True when the else branch is an elif written at the same indentation (parsed trees)."""
    return (
        len(node.orelse) == 1
        and isinstance(node.orelse[0], ast.If)
        and getattr(node.orelse[0], "col_offset", None) == getattr(node, "col_offset", None)
        and getattr(node, "col_offset", None) is not None
    )


def _block_depth(stmts: list[ast.stmt], level: int) -> int:
    deepest = level
    for stmt in stmts:
        deepest = max(deepest, _stmt_depth(stmt, level))
    return deepest


def _stmt_depth(stmt: ast.stmt, level: int) -> int:
    if isinstance(stmt, ast.If):
        inner = level + 1
        deepest = max(inner, _block_depth(stmt.body, inner))
        if _is_elif(stmt):
            return max(deepest, _stmt_depth(stmt.orelse[0], level))
        return max(deepest, _block_depth(stmt.orelse, inner))
    if isinstance(stmt, BLOCK_TYPES):
        inner = level + 1
        deepest = inner
        for name in ("body", "orelse", "finalbody"):
            deepest = max(deepest, _block_depth(getattr(stmt, name, None) or [], inner))
        for handler in getattr(stmt, "handlers", None) or []:
            deepest = max(deepest, _block_depth(handler.body, inner))
        for case in getattr(stmt, "cases", None) or []:
            deepest = max(deepest, _block_depth(case.body, inner))
        return deepest
    return level


def nesting_depth(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Maximum number of enclosing control blocks; an elif counts at its if's level."""
    return _block_depth(func.body, 0)


def code_nesting_depth(code: str) -> int | None:
    func, _ = parse_function(code)
    return None if func is None else nesting_depth(func)


def always_exits(stmts: list[ast.stmt]) -> bool:
    """True when the block always ends in return or raise on every path."""
    if not stmts:
        return False
    last = stmts[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return True
    if isinstance(last, ast.If):
        return bool(last.orelse) and always_exits(last.body) and always_exits(last.orelse)
    return False


def _count_statements(stmts: list[ast.stmt]) -> int:
    return sum(1 for stmt in stmts for node in ast.walk(stmt) if isinstance(node, ast.stmt))


def _weight(stmts: list[ast.stmt]) -> tuple[int, int]:
    return _block_depth(stmts, 0), _count_statements(stmts)


def _numeric_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    )


def negate(test: ast.expr) -> ast.expr:
    """Return the logical negation of a condition, simplified only when exact."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return test.operand
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        flipped = _EXACT_NEGATIONS.get(type(test.ops[0]))
        if flipped is None and (
            _numeric_literal(test.left) or _numeric_literal(test.comparators[0])
        ):
            flipped = _ORDER_NEGATIONS.get(type(test.ops[0]))
        if flipped is not None:
            return ast.Compare(left=test.left, ops=[flipped()], comparators=test.comparators)
    return ast.UnaryOp(op=ast.Not(), operand=test)


def _plan(stmt: ast.If) -> str | None:
    """Which guard rewrite applies: 'keep' (body exits), 'invert' (else exits), or None."""
    if not stmt.orelse:
        return None
    body_exits = always_exits(stmt.body)
    else_exits = always_exits(stmt.orelse)
    elif_chain = _is_elif(stmt)
    if body_exits and else_exits and not elif_chain:
        return "invert" if _weight(stmt.orelse) < _weight(stmt.body) else "keep"
    if body_exits:
        return "keep"
    if else_exits and not elif_chain:
        return "invert"
    return None


def _rewrite_children(node: ast.If) -> ast.If:
    """Recurse into an if statement without restructuring it, keeping elif chains flat."""
    if _is_elif(node):
        orelse: list[ast.stmt] = [_rewrite_children(node.orelse[0])]
    else:
        orelse = _transform_block(node.orelse)
    return ast.If(test=node.test, body=_transform_block(node.body), orelse=orelse)


def _transform_block(stmts: list[ast.stmt]) -> list[ast.stmt]:
    out: list[ast.stmt] = []
    for stmt in stmts:
        if not isinstance(stmt, ast.If):
            out.append(stmt)
            continue
        plan = _plan(stmt)
        if plan == "keep":
            out.append(ast.If(test=stmt.test, body=_transform_block(stmt.body), orelse=[]))
            out.extend(_transform_block(stmt.orelse))
        elif plan == "invert":
            out.append(
                ast.If(test=negate(stmt.test), body=_transform_block(stmt.orelse), orelse=[])
            )
            out.extend(_transform_block(stmt.body))
        else:
            out.append(_rewrite_children(stmt))
    return out


def to_guard_clauses(code: str) -> str | None:
    """Deterministic reference transformation, or None when the input is not a function.

    The result is normalized by ast.unparse, so comments and original formatting are not
    preserved. Behavior preservation assumes numeric operands are not NaN.
    """
    func, _ = parse_function(code)
    if func is None:
        return None
    func.body = _transform_block(func.body)
    module = ast.Module(body=[func], type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.unparse(module) + "\n"


def normalize(code: str) -> str | None:
    try:
        return ast.unparse(ast.parse(code)) + "\n"
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def same_code(left: str, right: str) -> bool:
    """Structural equality ignoring formatting and comments."""
    try:
        return ast.dump(ast.parse(left)) == ast.dump(ast.parse(right))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False


def _opportunity(stmt: ast.If, plan: str) -> Opportunity | None:
    dedented = stmt.orelse if plan == "keep" else stmt.body
    if _block_depth(dedented, 0) == 0:
        return None
    line = (stmt.orelse[-1] if plan == "invert" else stmt.body[-1]).lineno
    branch = "else branch" if plan == "invert" else "if branch"
    return Opportunity(
        start_line=stmt.lineno,
        end_line=stmt.end_lineno or stmt.lineno,
        reason=(
            f"The {branch} ending near line {line} always returns or raises, "
            "so it can become a guard clause and the remaining logic "
            "can be dedented."
        ),
    )


def _walk_conditionals(stmts: list[ast.stmt], found: list[Opportunity]) -> None:
    """Report the rewrites to_guard_clauses applies; mirrors _transform_block."""
    for stmt in stmts:
        if not isinstance(stmt, ast.If):
            continue
        plan = _plan(stmt)
        if plan is None:
            _walk_children(stmt, found)
            continue
        opportunity = _opportunity(stmt, plan)
        if opportunity is not None:
            found.append(opportunity)
        _walk_conditionals(stmt.body, found)
        _walk_conditionals(stmt.orelse, found)


def _walk_children(node: ast.If, found: list[Opportunity]) -> None:
    """Mirror _rewrite_children: an elif inside an unplanned chain is never restructured."""
    _walk_conditionals(node.body, found)
    if _is_elif(node):
        _walk_children(node.orelse[0], found)
    else:
        _walk_conditionals(node.orelse, found)


def check_input(code: str) -> InputCheck:
    """Decide whether the input is inside the supported task scope."""
    if len(code) > MAX_INPUT_CHARS or len(code.splitlines()) > MAX_INPUT_LINES:
        return InputCheck(supported=False, reasons=["too_long"])
    try:
        return _check_input(code)
    except RecursionError:
        return InputCheck(supported=False, reasons=["too_complex"])


def _check_input(code: str) -> InputCheck:
    func, reason = parse_function(code)
    if func is None:
        return InputCheck(supported=False, reasons=[reason])
    reasons = constraint_violations(func)
    depth = nesting_depth(func)
    if reasons:
        return InputCheck(False, reasons, func.name, depth)
    found: list[Opportunity] = []
    _walk_conditionals(func.body, found)
    transformed = to_guard_clauses(code)
    new_depth = code_nesting_depth(transformed) if transformed else None
    # The reference rewrite must itself create a guard clause: a depth drop that comes
    # only from ast.unparse printing "else: if" as "elif" is not a supported case.
    if not found or new_depth is None or new_depth >= depth or not rubric(code, transformed).passed:
        return InputCheck(False, ["no_opportunity"], func.name, depth)
    return InputCheck(True, [], func.name, depth, found)


def _has_guard_clause(stmts: list[ast.stmt]) -> bool:
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            if not stmt.orelse and always_exits(stmt.body):
                return True
            if _has_guard_clause(stmt.body):
                return True
            if _is_elif(stmt):
                if _elif_chain_has_guard(stmt.orelse[0]):
                    return True
            elif _has_guard_clause(stmt.orelse):
                return True
    return False


def _elif_chain_has_guard(node: ast.If) -> bool:
    """Guards inside an elif chain; the trailing elif itself is not a guard clause."""
    if _has_guard_clause(node.body):
        return True
    if _is_elif(node):
        return _elif_chain_has_guard(node.orelse[0])
    return _has_guard_clause(node.orelse)


def _called_names(func: ast.AST) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


RUBRIC_CHECKS = (
    "parses_as_single_function",
    "same_name",
    "same_signature",
    "same_docstring",
    "within_task_constraints",
    "nesting_reduced",
    "has_guard_clause",
    "no_new_calls",
)


def rubric(original: str, candidate: str) -> RubricResult:
    """Task-specific structural rubric. Passing it is not evidence of equal behavior."""
    original_func, _ = parse_function(original)
    if original_func is None:
        raise ValueError("The original code must be a single parseable function")
    candidate_func, reason = parse_function(candidate)
    if candidate_func is None:
        checks = dict.fromkeys(RUBRIC_CHECKS, False)
        return RubricResult(False, checks, [reason_text(reason or "syntax_error")])
    violations = constraint_violations(candidate_func)
    new_calls = _called_names(candidate_func) - _called_names(original_func)
    checks = {
        "parses_as_single_function": True,
        "same_name": candidate_func.name == original_func.name,
        "same_signature": (
            ast.dump(candidate_func.args) == ast.dump(original_func.args)
            and ast.dump(candidate_func.returns or ast.Constant(None))
            == ast.dump(original_func.returns or ast.Constant(None))
        ),
        "same_docstring": ast.get_docstring(candidate_func) == ast.get_docstring(original_func),
        "within_task_constraints": not violations,
        "nesting_reduced": nesting_depth(candidate_func) < nesting_depth(original_func),
        "has_guard_clause": _has_guard_clause(candidate_func.body),
        "no_new_calls": not new_calls,
    }
    reasons = []
    if not checks["same_name"]:
        reasons.append(f"Function renamed from {original_func.name} to {candidate_func.name}.")
    if not checks["same_signature"]:
        reasons.append("The parameters or return annotation changed.")
    if not checks["same_docstring"]:
        reasons.append("The docstring changed.")
    if violations:
        reasons.extend(reason_text(code) for code in violations)
    if not checks["nesting_reduced"]:
        reasons.append(
            f"Nesting depth did not decrease ({nesting_depth(original_func)} -> "
            f"{nesting_depth(candidate_func)})."
        )
    if not checks["has_guard_clause"]:
        reasons.append("No guard clause (an if without else that returns or raises) was found.")
    if new_calls:
        reasons.append(f"New calls were introduced: {', '.join(sorted(new_calls))}.")
    return RubricResult(all(checks.values()), checks, reasons)

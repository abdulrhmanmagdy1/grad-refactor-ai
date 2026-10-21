"""Static admission policy applied before a candidate is handed to the test process.

The reference runner executes model-generated candidates against server-owned cases.
Before anything is executed, the candidate must parse as exactly one top-level function
inside the guard_clauses task constraints (no imports, nested definitions, dunder access
or denied builtins). On top of the task constraints the runner also refuses:

- any reference to a denied builtin, not only a direct call (``f = eval`` is refused),
  unless the name is a parameter or a variable assigned in the function;
- getattr/hasattr/setattr/delattr unless the attribute name is a string literal that
  does not start with an underscore, which closes the usual introspection route to
  ``__class__``, ``__globals__`` or ``__builtins__`` through computed names.

This is one layer of several (see docs/development/runner-safety.md). It inspects syntax
trees only and never executes anything.
"""

from __future__ import annotations

import ast

from refactor_ai.tasks import guard_clauses

ATTRIBUTE_BUILTINS = frozenset({"getattr", "hasattr", "setattr", "delattr"})
DYNAMIC_ATTRIBUTE = "dynamic_attribute_access"

POLICY_TEXT = {
    DYNAMIC_ATTRIBUTE: (
        "getattr, hasattr, setattr and delattr are allowed only with a literal attribute "
        "name that does not start with an underscore."
    ),
}


def describe(code: str) -> str:
    """Human-readable text for a task or runner policy code, phrased for a candidate."""
    if code.startswith("denied_name:"):
        return f"References to {code.split(':', 1)[1]} are outside the runner policy."
    text = POLICY_TEXT.get(code) or guard_clauses.reason_text(code)
    return "The candidate " + text[len("The input ") :] if text.startswith("The input ") else text


def _literal_public_name(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and not node.value.startswith("_")
    )


def _bound_names(func: ast.AST) -> set[str]:
    """Parameters and assigned names; inside the function they never mean a builtin."""
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
    return names


def admission_problems(candidate: str) -> list[str]:
    """Reason codes that keep a candidate out of the test process; empty when admitted.

    The only code is syntax_error or not_single_function when the candidate is not a
    single parseable function; such a candidate cannot define the function under test.
    """
    func, reason = guard_clauses.parse_function(candidate)
    if func is None:
        return [reason or "syntax_error"]
    problems = list(guard_clauses.constraint_violations(func))
    bound = _bound_names(func)
    called: set[int] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(id(node.func))
            if (
                node.func.id in ATTRIBUTE_BUILTINS
                and node.func.id not in bound
                and (len(node.args) < 2 or node.keywords or not _literal_public_name(node.args[1]))
            ):
                problems.append(DYNAMIC_ATTRIBUTE)
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and (node.id in guard_clauses.DENIED_CALLS or node.id in ATTRIBUTE_BUILTINS)
            and node.id not in bound
            and id(node) not in called
        ):
            problems.append(f"denied_name:{node.id}")
    return list(dict.fromkeys(problems))

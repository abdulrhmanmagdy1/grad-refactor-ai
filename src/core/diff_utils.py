"""Unified diff generator and structural component inspection utilities."""

import ast
import difflib

from core.schemas import DiffOutput


def extract_top_level_symbols(code: str) -> set[str]:
    """Extract top-level and nested function/class names safely via AST."""
    symbols: set[str] = set()
    try:
        tree = ast.parse(code)
    except Exception:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
    return symbols


def format_call_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render an argument-name-only signature used for caller compatibility checks.

    Defaults and annotations are deliberately excluded: normalising a mutable
    default (``store=[]`` -> ``store=None``) legitimately changes the default
    value while every existing call site stays valid.
    """
    args = node.args
    parts: list[str] = [arg.arg for arg in args.posonlyargs]
    if args.posonlyargs:
        parts.append("/")
    parts.extend(arg.arg for arg in args.args)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    parts.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(parts)})"


def extract_symbol_signatures(code: str) -> dict[str, str]:
    """Map qualified symbol names to their call-compatibility signatures.

    Qualified names distinguish module functions (``f``), methods
    (``Class.method``), and nested functions (``outer.inner``).
    """
    signatures: dict[str, str] = {}
    try:
        tree = ast.parse(code)
    except Exception:
        return signatures

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + child.name
                signatures[qualified] = format_call_signature(child)
                visit(child, qualified + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, prefix + child.name + ".")

    visit(tree, "")
    return signatures


def generate_diff(
    original_code: str, refactored_code: str, filename: str = "target.py"
) -> DiffOutput:
    """Generate a structured unified diff with line counts and affected components."""
    orig_lines = original_code.splitlines(keepends=True)
    refact_lines = refactored_code.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            orig_lines,
            refact_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
    )
    diff_text = "".join(diff_lines)

    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

    # Syntax check on refactored code
    syntax_valid = True
    try:
        ast.parse(refactored_code)
    except Exception:
        syntax_valid = False

    orig_symbols = extract_top_level_symbols(original_code)
    refact_symbols = extract_top_level_symbols(refactored_code)
    affected = sorted(list(orig_symbols.symmetric_difference(refact_symbols) or orig_symbols))

    return DiffOutput(
        diff=diff_text,
        original_code=original_code,
        refactored_code=refactored_code,
        added_lines=added,
        removed_lines=removed,
        modified_components=affected,
        syntax_valid=syntax_valid,
    )

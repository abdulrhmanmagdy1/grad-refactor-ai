"""Applying a proposed function to its file, the diff, and the static re-check of a fix.

A fix replaces one function's lines, from its `def` line to its last line, with the
proposed function indented like the original; decorators and the rest of the file stay as
they are. The static re-check runs ruff (from standard input) and the project rules on the
file before and after the fix and compares the findings inside the function: the finding
being fixed must be gone, and no new finding may appear. A guard-clause fix must pass the
task rubric instead.
"""

from __future__ import annotations

import ast
import difflib
import json
import subprocess
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass

from refactor_ai.project import rules, static
from refactor_ai.project.models import Finding, FixCheck
from refactor_ai.tasks import guard_clauses


@dataclass(frozen=True)
class Span:
    """The lines of one function in its file: `def` line to last line, and its indent."""

    def_line: int
    end_line: int
    indent: str


@dataclass(frozen=True)
class AppliedFix:
    patched: str
    span_after: Span
    diff: str


class FixError(ValueError):
    """The proposal cannot be applied (the reason is shown as a failed syntax check)."""


def function_span(source: str, name: str, end_line: int) -> Span | None:
    """The span of the function `name` whose last line is `end_line`."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None
    lines = source.splitlines()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
            and node.end_lineno == end_line
        ):
            text = lines[node.lineno - 1]
            return Span(node.lineno, end_line, text[: len(text) - len(text.lstrip())])
    return None


def function_text(source: str, span: Span) -> str:
    lines = source.splitlines()
    return textwrap.dedent("\n".join(lines[span.def_line - 1 : span.end_line])) + "\n"


@dataclass(frozen=True)
class Proposal:
    """A proposed function (from its `def` line) and the imports it needs at module level."""

    function: str
    imports: tuple[str, ...] = ()
    # Other classes and functions the model wrote around the function, which are ignored.
    dropped: tuple[str, ...] = ()


_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def check_proposal(proposed: str, name: str) -> Proposal:
    """One function named `name`, with any import statements it needs.

    Models often wrap the function in its class or add stand-in definitions of the names it
    uses; those other classes and functions are dropped (the static re-check then reports
    anything the function really needed from them). Other module-level code is refused.
    """
    text = textwrap.dedent(proposed)
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise FixError(f"The proposed function does not parse: {exc}") from exc
    shape = "The proposal must be one function, optionally preceded by imports."
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    if any(not isinstance(n, (*_DEFINITIONS, ast.Import, ast.ImportFrom)) for n in tree.body):
        raise FixError(shape)
    candidates = [
        n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ] or [
        child
        for n in tree.body
        if isinstance(n, ast.ClassDef)
        for child in n.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    named = [n for n in candidates if n.name == name]
    if len(named) > 1:
        raise FixError(shape)
    if not named:
        if candidates:
            raise FixError(f"The proposal renames the function to {candidates[0].name}.")
        raise FixError(shape)
    target = named[0]
    lines = text.splitlines()
    function = textwrap.dedent("\n".join(lines[target.lineno - 1 : target.end_lineno]) + "\n")
    dropped = tuple(n.name for n in tree.body if isinstance(n, _DEFINITIONS) and n is not target)
    return Proposal(
        function,
        tuple(" ".join(ast.get_source_segment(text, node).split()) for node in imports),
        dropped,
    )


def _import_position(tree: ast.Module) -> int:
    """Index (0-based line) after the last top-level import, or after the module docstring."""
    position = 0
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        position = body[0].end_lineno or 0
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            position = node.end_lineno or position
    return position


def apply_fix(source: str, file: str, span: Span, proposal: Proposal | str) -> AppliedFix:
    """The file with the function replaced (and missing imports added), the new span of
    the function and a unified diff of the file."""
    if isinstance(proposal, str):
        proposal = Proposal(proposal)
    body = textwrap.dedent(proposal.function).strip("\n").splitlines()
    newline = "\r\n" if "\r\n" in source else "\n"
    replacement = [(span.indent + line) if line.strip() else "" for line in body]
    lines = source.splitlines()
    patched_lines = lines[: span.def_line - 1] + replacement + lines[span.end_line :]
    shift = 0
    if proposal.imports:
        tree = ast.parse(source)
        existing = {
            " ".join(ast.get_source_segment(source, node).split())
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        }
        missing = [line for line in proposal.imports if line not in existing]
        position = min(_import_position(tree), span.def_line - 1)
        patched_lines[position:position] = missing
        shift = len(missing)
    patched = newline.join(patched_lines) + (newline if source.endswith(("\n", "\r")) else "")
    diff = unified_diff(source, patched, file)
    start = span.def_line + shift
    return AppliedFix(patched, Span(start, start + len(replacement) - 1, span.indent), diff)


def unified_diff(before: str, after: str, file: str) -> str:
    return "".join(
        difflib.unified_diff(
            [line + "\n" for line in before.splitlines()],
            [line + "\n" for line in after.splitlines()],
            fromfile=f"a/{file}",
            tofile=f"b/{file}",
            n=3,
        )
    )


def ruff_source(source: str, file: str) -> tuple[list[dict], str | None]:
    """ruff's diagnostics for one file's text (read from standard input)."""
    command = [
        sys.executable,
        "-I",  # isolated: the project folder is never on the import path
        "-m",
        "ruff",
        "check",
        "--isolated",
        "--no-cache",
        "--exit-zero",
        "--output-format",
        "json",
        "--target-version",
        "py311",
        "--line-length",
        "100",
        "--select",
        ",".join(static.RUFF_SELECT),
        "--ignore",
        ",".join(static.RUFF_IGNORE),
        "--stdin-filename",
        file,
        "-",
    ]
    try:
        completed = subprocess.run(
            command,
            input=source.encode("utf-8"),
            capture_output=True,
            timeout=static.RUFF_TIMEOUT_S,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"ruff could not run: {type(exc).__name__}"
    if completed.returncode != 0:
        return [], "ruff failed"
    try:
        return json.loads(completed.stdout.decode("utf-8") or "[]"), None
    except json.JSONDecodeError:
        return [], "ruff returned output that is not JSON"


def _codes_in(source: str, file: str, span: Span) -> tuple[Counter, str | None]:
    """Rule identifiers found inside the span: ruff codes and project rule names."""
    diagnostics, problem = ruff_source(source, file)
    codes: Counter = Counter()
    for item in diagnostics:
        row = (item.get("location") or {}).get("row") or 0
        if span.def_line <= row <= span.end_line:
            codes[f"ruff:{item.get('code') or 'syntax-error'}"] += 1
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return codes, problem
    for hit in rules.check(tree):
        if span.def_line <= hit.line <= span.end_line:
            codes[f"rule:{hit.rule}"] += 1
    return codes, problem


def target_rule(finding: Finding) -> str | None:
    """The rule identifier that must disappear for a static finding, else None."""
    if finding.source.startswith("static:ruff:"):
        return "ruff:" + finding.source.removeprefix("static:ruff:")
    if finding.source.startswith("static:rule:"):
        return "rule:" + finding.source.removeprefix("static:rule:")
    return None


def static_recheck(
    findings: list[Finding],
    file: str,
    before: str,
    span_before: Span,
    applied: AppliedFix,
) -> FixCheck:
    """pass when the findings' rules are gone and nothing new appears in the function;
    partial when some are gone and nothing new appears; fail otherwise."""
    if any(f.source == "static:task:guard_clauses" for f in findings):
        result = guard_clauses.rubric(
            function_text(before, span_before), function_text(applied.patched, applied.span_after)
        )
        if not result.passed:
            failed = [name for name, passed in result.checks.items() if not passed]
            return FixCheck(status="fail", detail="Rubric checks failed: " + ", ".join(failed))
    old, problem = _codes_in(before, file, span_before)
    new, problem_after = _codes_in(applied.patched, file, applied.span_after)
    if problem or problem_after:
        return FixCheck(status="not_run", detail=problem or problem_after)
    targets = Counter(t for t in (target_rule(f) for f in findings) if t)
    added = new - old
    for target in targets:
        added.pop(target, None)
    if added:
        names = ", ".join(sorted(code.split(":", 1)[1] for code in added))
        return FixCheck(status="fail", detail=f"The fix adds new findings: {names}.")
    still = sorted(t for t in targets if new.get(t, 0) > max(0, old.get(t, 0) - targets[t]))
    gone = sorted(t for t in targets if t not in still)
    label = ", ".join
    if still and not gone:
        names = label(t.split(":", 1)[1] for t in still)
        return FixCheck(status="fail", detail=f"Still reported: {names}.")
    if still:
        return FixCheck(
            status="partial",
            detail=f"Gone: {label(t.split(':', 1)[1] for t in gone)}; still reported: "
            f"{label(t.split(':', 1)[1] for t in still)}; no new static findings.",
        )
    if targets:
        names = label(t.split(":", 1)[1] for t in gone)
        return FixCheck(status="pass", detail=f"{names}: gone; no new static findings.")
    return FixCheck(status="pass", detail="No new static findings.")

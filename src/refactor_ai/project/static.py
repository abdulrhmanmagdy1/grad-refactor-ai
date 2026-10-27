"""Deterministic findings: ruff, mypy, the project rules, the index metrics and the
guard-clause task.

ruff runs as a separate process on the workspace with a fixed rule selection and no
configuration from the project (`--isolated`); it parses files and never executes them.
Each finding gets a category, a severity and whether it can be fixed inside one function.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from refactor_ai.project import rules
from refactor_ai.project.index import FunctionInfo, ProjectIndex
from refactor_ai.project.models import Category, Finding, Severity
from refactor_ai.project.workspace import Workspace
from refactor_ai.tasks import guard_clauses

RUFF_TIMEOUT_S = 120
RUFF_SELECT = (
    "F",
    "E711",
    "E712",
    "E721",
    "E722",
    "B",
    "S",
    "PLE",
    "PLW",
    "ARG",
    "SIM",
    "PERF",
    "RET",
    "PLR0911",
    "PLR0912",
    "PLR0913",
    "PLR0915",
)
# assert is normal in tests; an unused loop variable and missing zip(strict=) are noise here.
RUFF_IGNORE = ("S101", "B905", "B007", "RET505", "RET506", "SIM108")

BUG_RULES = frozenset(
    {
        "F402", "F502", "F503", "F504", "F505", "F506", "F507", "F508", "F509", "F521",
        "F522", "F523", "F524", "F525", "F601", "F602", "F631", "F632", "F701", "F702",
        "F704", "F706", "F707", "F811", "F821", "F822", "F823", "F901",
        "B002", "B006", "B008", "B011", "B012", "B015", "B016", "B018", "B020", "B023",
        "B025", "B026", "B029", "B030", "B032", "B033", "B035",
        "PLW0120", "PLW0127", "PLW0128", "PLW0129", "PLW0131", "PLW0177", "PLW0211",
        "PLW0711", "PLW1501", "PLW1508", "PLW2101", "PLW3301",
    }
)  # fmt: skip
HIGH_RULES = frozenset(
    {
        "F821", "F822", "F823", "F632", "F811", "B012", "B020", "B023", "B006",
        "S102", "S307", "S301", "S506", "S602", "S605", "S608", "S701",
    }
)  # fmt: skip
LOW_SECURITY_RULES = frozenset({"S110", "S112", "S311", "S105", "S106", "S107"})
MEDIUM_QUALITY_RULES = frozenset({"E722", "PLR0912", "PLR0915", "PLW0603", "B904"})

# Index thresholds.
LONG_FUNCTION_LINES = 60
HIGH_COMPLEXITY = 10
VERY_HIGH_COMPLEXITY = 20
DEEP_NESTING = 4
MANY_PARAMETERS = 6
LARGE_MODULE_LINES = 400
LARGE_MODULE_FUNCTIONS = 30
HUB_FAN_OUT = 8


def classify_ruff(code: str | None) -> tuple[Category, Severity]:
    if code is None:
        return Category.BUG, Severity.HIGH  # a syntax error
    if code[:1] == "S" and code[1:2].isdigit():  # bandit (S101...), not simplify (SIM...)
        if code in HIGH_RULES:
            return Category.SECURITY, Severity.HIGH
        if code in LOW_SECURITY_RULES:
            return Category.SECURITY, Severity.LOW
        return Category.SECURITY, Severity.MEDIUM
    if code in BUG_RULES or code.startswith("PLE") or code.startswith("E9"):
        return Category.BUG, Severity.HIGH if code in HIGH_RULES or code.startswith(
            "PLE"
        ) else Severity.MEDIUM
    if code in MEDIUM_QUALITY_RULES:
        return Category.QUALITY, Severity.MEDIUM
    return Category.QUALITY, Severity.LOW


def run_ruff(workspace: Workspace) -> tuple[list[dict], str | None]:
    """ruff's JSON diagnostics for the workspace, or ([], reason) when ruff cannot run."""
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
        ",".join(RUFF_SELECT),
        "--ignore",
        ",".join(RUFF_IGNORE),
        ".",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=workspace.root,
            capture_output=True,
            timeout=RUFF_TIMEOUT_S,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"ruff could not run: {type(exc).__name__}"
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        return [], f"ruff failed: {detail[-1] if detail else completed.returncode}"
    try:
        diagnostics = json.loads(completed.stdout.decode("utf-8") or "[]")
    except json.JSONDecodeError:
        return [], "ruff returned output that is not JSON"
    root = workspace.root
    for item in diagnostics:
        try:
            item["file"] = Path(item["filename"]).resolve().relative_to(root).as_posix()
        except (KeyError, ValueError):
            item["file"] = None
    return [item for item in diagnostics if item.get("file")], None


def enclosing_function(index: ProjectIndex, file: str, line: int) -> FunctionInfo | None:
    """The innermost function of `file` whose lines contain `line`."""
    module = index.by_file.get(file)
    if module is None:
        return None
    holding = [f for f in module.functions if f.line_start <= line <= f.line_end]
    return min(holding, key=lambda f: f.lines) if holding else None


def _symbol(index: ProjectIndex, file: str, line: int) -> str | None:
    function = enclosing_function(index, file, line)
    if function is not None:
        return function.qualname
    module = index.by_file.get(file)
    return module.name if module else None


def ruff_findings(diagnostics: list[dict], index: ProjectIndex) -> list[Finding]:
    found = []
    for item in diagnostics:
        code = item.get("code")
        category, severity = classify_ruff(code)
        line = item.get("location", {}).get("row") or 1
        end = item.get("end_location", {}).get("row") or line
        file = item["file"]
        in_function = enclosing_function(index, file, line) is not None
        title = item.get("message", "").split("\n")[0].strip() or "Syntax error"
        found.append(
            Finding(
                id="",
                category=category,
                severity=severity,
                source=f"static:ruff:{code or 'syntax-error'}",
                file=file,
                line_start=line,
                line_end=max(line, end),
                symbol=_symbol(index, file, line),
                title=title,
                explanation=item.get("message", title),
                evidence=f"ruff {code}" + (f" ({item['url']})" if item.get("url") else "")
                if code
                else "Python could not parse this file.",
                fixable=in_function and code is not None and category is not Category.ARCHITECTURE,
            )
        )
    return found


RULE_INFO = {
    "iterated-list-mutated": (
        Category.BUG,
        Severity.HIGH,
        "A list is changed while it is iterated",
    ),
    "identity-comparison-of-computed-value": (
        Category.BUG,
        Severity.MEDIUM,
        "Identity comparison of a computed value",
    ),
    "value-never-used": (Category.QUALITY, Severity.LOW, "A value is computed but never used"),
}


def rule_findings(workspace: Workspace, index: ProjectIndex) -> list[Finding]:
    found = []
    for module in index.modules.values():
        if module.parse_error:
            continue
        tree = ast.parse(workspace.read(module.file))
        for hit in rules.check(tree):
            category, severity, title = RULE_INFO[hit.rule]
            found.append(
                Finding(
                    id="",
                    category=category,
                    severity=severity,
                    source=f"static:rule:{hit.rule}",
                    file=module.file,
                    line_start=hit.line,
                    line_end=hit.end_line,
                    symbol=_symbol(index, module.file, hit.line),
                    title=title,
                    explanation=hit.message,
                    evidence=f"project rule {hit.rule}",
                    fixable=enclosing_function(index, module.file, hit.line) is not None,
                )
            )
    return found


def index_findings(index: ProjectIndex) -> list[Finding]:
    found = []

    def add(**fields) -> None:
        found.append(Finding(id="", **fields))

    for cycle in index.cycles:
        first = index.modules[cycle[0]]
        add(
            category=Category.ARCHITECTURE,
            severity=Severity.HIGH,
            source="static:index:import-cycle",
            file=first.file,
            symbol=cycle[0],
            title="Import cycle between modules",
            explanation="These modules import each other, directly or through others: "
            + " -> ".join([*cycle, cycle[0]])
            + ". Cycles make import order fragile and the modules impossible to use alone.",
            evidence="internal import graph",
            recommendation="Move the shared code into a module that the others import, or "
            "invert one dependency so the graph has no cycle.",
        )
    for module in index.modules.values():
        if module.parse_error:
            add(
                category=Category.BUG,
                severity=Severity.HIGH,
                source="static:index:parse-error",
                file=module.file,
                symbol=module.name,
                title="The file is not valid Python",
                explanation=module.parse_error,
                evidence="ast.parse",
            )
            continue
        if module.is_test:
            continue
        functions = len(module.functions)
        if module.code_lines > LARGE_MODULE_LINES or functions > LARGE_MODULE_FUNCTIONS:
            add(
                category=Category.ARCHITECTURE,
                severity=Severity.MEDIUM,
                source="static:index:large-module",
                file=module.file,
                symbol=module.name,
                title="Large module with many responsibilities",
                explanation=f"{module.name} has {module.code_lines} code lines and {functions} "
                "functions, which usually means several responsibilities in one place.",
                evidence=f"{module.code_lines} code lines, {functions} functions",
                recommendation="Split it by responsibility into smaller modules.",
            )
        if index.fan_out[module.name] >= HUB_FAN_OUT:
            add(
                category=Category.ARCHITECTURE,
                severity=Severity.LOW,
                source="static:index:high-fan-out",
                file=module.file,
                symbol=module.name,
                title="Module depends on many other modules",
                explanation=f"{module.name} imports {index.fan_out[module.name]} project modules, "
                "so a change in any of them can affect it.",
                evidence=", ".join(sorted(module.imports)),
                recommendation="Check whether it mixes coordination with details that belong in "
                "the modules it imports.",
            )
        for function in module.functions:
            add_function_metrics(add, function)
    for group in index.duplicates:
        first = group[0]
        places = ", ".join(f"{f.file}:{f.line_start} {f.qualname}" for f in group)
        add(
            category=Category.QUALITY,
            severity=Severity.MEDIUM,
            source="static:index:duplicate-function",
            file=first.file,
            line_start=first.line_start,
            line_end=first.line_end,
            symbol=first.qualname,
            title="Duplicated function body",
            explanation=f"{len(group)} functions have the same body: {places}.",
            evidence="identical syntax trees",
            recommendation="Keep one implementation and call it from the other places.",
        )
    if not index.has_tests and index.functions:
        add(
            category=Category.QUALITY,
            severity=Severity.LOW,
            source="static:index:no-tests",
            title="No tests found",
            explanation="The project has no test files, so no change to it can be checked by "
            "running tests.",
            evidence="no test_*.py, *_test.py or tests/ folder",
            recommendation="Add pytest tests for the main functions.",
        )
    return found


def add_function_metrics(add, function: FunctionInfo) -> None:
    common = {
        "file": function.file,
        "line_start": function.line_start,
        "line_end": function.line_end,
        "symbol": function.qualname,
    }
    if function.complexity > HIGH_COMPLEXITY:
        add(
            category=Category.QUALITY,
            severity=Severity.HIGH
            if function.complexity > VERY_HIGH_COMPLEXITY
            else Severity.MEDIUM,
            source="static:index:high-complexity",
            title="Function is hard to follow",
            explanation=f"{function.qualname} has a cyclomatic complexity of "
            f"{function.complexity} (more than {HIGH_COMPLEXITY} paths through it).",
            evidence=f"complexity {function.complexity}",
            recommendation="Extract parts into helper functions or return early.",
            **common,
        )
    if function.lines > LONG_FUNCTION_LINES:
        add(
            category=Category.QUALITY,
            severity=Severity.MEDIUM,
            source="static:index:long-function",
            title="Long function",
            explanation=f"{function.qualname} spans {function.lines} lines.",
            evidence=f"{function.lines} lines",
            recommendation="Split it into smaller functions with one job each.",
            **common,
        )
    if function.nesting >= DEEP_NESTING:
        add(
            category=Category.QUALITY,
            severity=Severity.MEDIUM,
            source="static:index:deep-nesting",
            title="Deeply nested control flow",
            explanation=f"{function.qualname} nests control blocks {function.nesting} levels deep.",
            evidence=f"nesting depth {function.nesting}",
            recommendation="Return early (guard clauses) or extract the inner blocks.",
            **common,
        )
    if function.parameters > MANY_PARAMETERS:
        add(
            category=Category.QUALITY,
            severity=Severity.LOW,
            source="static:index:many-parameters",
            title="Function takes many parameters",
            explanation=f"{function.qualname} takes {function.parameters} parameters.",
            evidence=f"{function.parameters} parameters",
            recommendation="Group related parameters into an object.",
            **common,
        )


def function_source(workspace: Workspace, function: FunctionInfo) -> str:
    """The function's own lines from `def` to its end (decorators excluded), dedented."""
    lines = workspace.read(function.file).splitlines()
    module = ast.parse("\n".join(lines))
    for node in ast.walk(module):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.end_lineno == function.line_end
            and node.name == function.name
        ):
            return textwrap.dedent("\n".join(lines[node.lineno - 1 : node.end_lineno])) + "\n"
    return textwrap.dedent("\n".join(lines[function.line_start - 1 : function.line_end])) + "\n"


def task_findings(workspace: Workspace, index: ProjectIndex) -> list[Finding]:
    """Functions that the guard-clause task can flatten (fixed by the deterministic rewrite)."""
    found = []
    for function in index.functions:
        if function.is_test or function.lines > guard_clauses.MAX_INPUT_LINES:
            continue
        source = function_source(workspace, function)
        check = guard_clauses.check_input(source)
        if not check.supported:
            continue
        before = function.nesting
        after = guard_clauses.code_nesting_depth(guard_clauses.to_guard_clauses(source) or "")
        found.append(
            Finding(
                id="",
                category=Category.REFACTORING,
                severity=Severity.LOW,
                source="static:task:guard_clauses",
                file=function.file,
                line_start=function.line_start,
                line_end=function.line_end,
                symbol=function.qualname,
                title="Nested conditional can be flattened with guard clauses",
                explanation=f"{function.qualname} nests if/else blocks where a branch always "
                "returns or raises; returning early would reduce the nesting"
                + (f" from {before} to {after}." if after is not None else "."),
                evidence="guard_clauses.check_input",
                recommendation="Replace Nested Conditional with Guard Clauses (Fowler).",
                fixable=True,
            )
        )
    return found


def scan(workspace: Workspace, index: ProjectIndex) -> tuple[list[Finding], list[str]]:
    """Every deterministic finding and any warnings (for example, ruff unavailable)."""
    warnings = []
    diagnostics, problem = run_ruff(workspace)
    if problem:
        warnings.append(problem)
    from refactor_ai.project import typecheck

    errors, problem = typecheck.run_mypy(workspace.root, typecheck.checked_files(index))
    if problem:
        warnings.append(problem)
    findings = [
        *ruff_findings(diagnostics, index),
        *typecheck.mypy_findings(errors, index),
        *rule_findings(workspace, index),
        *index_findings(index),
        *task_findings(workspace, index),
    ]
    return findings, warnings

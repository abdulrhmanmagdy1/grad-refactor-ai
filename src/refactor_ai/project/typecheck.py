"""Type checking with mypy: wrong arguments, attributes that do not exist, None used as a
value and comparisons that can never be true, found from the project's own type hints.

mypy runs as a separate process on the workspace (or a copy with patched files). Like
ruff it reads the code and never executes it. Only error codes that point at a defect are
kept; codes about missing or loose annotations are left out, since a project without type
hints is not wrong.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from refactor_ai.project.index import ProjectIndex
from refactor_ai.project.models import Category, Finding, Severity

MYPY_TIMEOUT_S = 180
# Error codes that mean the code will fail or misbehave when it runs.
BUG_CODES = frozenset(
    {
        "arg-type",
        "call-arg",
        "call-overload",
        "attr-defined",
        "union-attr",
        "return-value",
        "operator",
        "index",
        "name-defined",
        "func-returns-value",
        "comparison-overlap",
        "str-bytes-safe",
        "has-type",
        "misc",
    }
)
HIGH_CODES = frozenset({"name-defined", "attr-defined", "call-arg"})
_LINE = re.compile(
    r"^(?P<file>[^:\n]+?):(?P<line>\d+):(?P<col>\d+): error: "
    r"(?P<message>.*?)\s+\[(?P<code>[a-z-]+)\]$"
)
EXPLAIN = {
    "arg-type": "A function is called with an argument of a type it does not accept.",
    "call-arg": "A function is called with missing, extra or misnamed arguments.",
    "call-overload": "No version of the called function accepts these arguments.",
    "attr-defined": "The code uses an attribute or method that the object does not have.",
    "union-attr": "A value that can be None (or another type) is used as if it never were.",
    "return-value": "The function returns a value of a type its signature does not allow.",
    "operator": "An operator is used on values that do not support it.",
    "index": "A value is indexed with a key or index of the wrong type.",
    "name-defined": "A name is used that is not defined.",
    "func-returns-value": "The result of a function that returns nothing is used.",
    "comparison-overlap": "Two values of types that can never be equal are compared.",
    "str-bytes-safe": "bytes are formatted into a string, which prints their repr.",
    "has-type": "The type of a value cannot be determined where it is used.",
    "misc": "mypy reports a type error.",
}


def run_mypy(
    root: Path, files: list[str], replacements: dict[str, str] | None = None
) -> tuple[list[dict], str | None]:
    """mypy's errors for `files` of the project at `root` (with `replacements` written into
    a copy first), as dicts with file, line, code and message; or ([], reason)."""
    if not files:
        return [], None
    with tempfile.TemporaryDirectory(prefix="mypy-") as temp:
        target = root
        if replacements:
            target = Path(temp) / "project"
            shutil.copytree(root, target)
            for relative, text in replacements.items():
                (target / relative).write_text(text, encoding="utf-8", newline="")
        config = Path(temp) / "mypy.ini"
        config.write_text("[mypy]\n", encoding="utf-8")
        command = [
            sys.executable,
            "-I",  # isolated: a mypy.py in the project cannot replace mypy
            "-m",
            "mypy",
            # Our own empty configuration: the project's mypy.ini, setup.cfg or pyproject.toml
            # (whose plugins= setting would run its code) is never read.
            "--config-file",
            str(config),
            "--no-error-summary",
            "--show-error-codes",
            "--show-column-numbers",
            "--no-pretty",
            "--hide-error-context",
            "--no-color-output",
            "--ignore-missing-imports",
            "--follow-imports=silent",
            "--explicit-package-bases",
            "--namespace-packages",
            "--check-untyped-defs",
            "--strict-equality",
            "--python-version",
            "3.11",
            "--cache-dir",
            str(Path(temp) / "cache"),
            "--",  # every name after this is a file, never an option
            *files,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=target,
                capture_output=True,
                timeout=MYPY_TIMEOUT_S,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [], f"mypy could not run: {type(exc).__name__}"
    if completed.returncode not in (0, 1):
        detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        return [], f"mypy failed: {detail[-1] if detail else completed.returncode}"
    errors = []
    for line in completed.stdout.decode("utf-8", errors="replace").splitlines():
        match = _LINE.match(line.strip())
        if match is None or match["code"] not in BUG_CODES:
            continue
        errors.append(
            {
                "file": Path(match["file"]).as_posix(),
                "line": int(match["line"]),
                "code": match["code"],
                "message": match["message"].strip(),
            }
        )
    return errors, None


def checked_files(index: ProjectIndex) -> list[str]:
    """The project's own modules that mypy checks (tests are left out)."""
    return sorted(m.file for m in index.modules.values() if not m.is_test and not m.parse_error)


def mypy_findings(errors: list[dict], index: ProjectIndex) -> list[Finding]:
    from refactor_ai.project.static import enclosing_function

    found = []
    for error in errors:
        file, line, code = error["file"], error["line"], error["code"]
        if file not in index.by_file:
            continue
        function = enclosing_function(index, file, line)
        found.append(
            Finding(
                id="",
                category=Category.BUG,
                severity=Severity.HIGH if code in HIGH_CODES else Severity.MEDIUM,
                source=f"static:mypy:{code}",
                file=file,
                line_start=line,
                line_end=line,
                symbol=function.qualname if function else index.by_file[file].name,
                title=error["message"][:120],
                explanation=f"{EXPLAIN.get(code, EXPLAIN['misc'])} mypy: {error['message']}",
                evidence=f"mypy [{code}]",
                fixable=function is not None,
            )
        )
    return found


def in_span(errors: list[dict], file: str, start: int, end: int) -> list[dict]:
    return [e for e in errors if e["file"] == file and start <= e["line"] <= end]

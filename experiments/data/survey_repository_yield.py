"""Exploratory yield survey of a public code repository for the guard_clauses task.

Not part of the dataset. It counts how many top-level functions of a pinned repository
snapshot pass guard_clauses.check_input and the rubric (and read no free globals), to
judge whether mining real repositories could replace template families. Reproduce:

    python -m uv run python experiments/data/survey_repository_yield.py

It downloads the pinned TheAlgorithms/Python archive (MIT, about 8.5 MB) into the
Git-ignored data/raw/ folder if missing, verifies its SHA-256, parses files with ast
only (nothing from the archive is executed) and writes survey-thealgorithms.json.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import sys
import tarfile
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from refactor_ai.tasks import guard_clauses  # noqa: E402

COMMIT = "6e03a48579ca212a08b36be00378f887dc41a003"
URL = f"https://codeload.github.com/TheAlgorithms/Python/tar.gz/{COMMIT}"
SHA256 = "8dea8df7d2faf42242714dc70da6bbc35639cc3ae93754d72d5a32e0530db463"
ARCHIVE = ROOT / "data" / "raw" / "thealgorithms" / f"Python-{COMMIT}.tar.gz"
OUTPUT = Path(__file__).with_name("survey-thealgorithms.json")


def free_names(func: ast.FunctionDef) -> list[str]:
    bound = {node.arg for node in ast.walk(func) if isinstance(node, ast.arg)}
    bound |= {
        node.id
        for node in ast.walk(func)
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del))
    }
    loads = {
        n.id for n in ast.walk(func) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    return sorted(loads - bound - set(dir(builtins)) - {func.name})


def main() -> int:
    if not ARCHIVE.exists():
        ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(URL, headers={"User-Agent": "grad-refactor-ai"})
        with urllib.request.urlopen(request, timeout=300) as response:
            ARCHIVE.write_bytes(response.read())
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"archive hash {digest} does not match {SHA256}")
    reasons: Counter = Counter()
    qualified = []
    files = functions = 0
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        for member in sorted(archive.getmembers(), key=lambda m: m.name):
            if not member.isfile() or not member.name.endswith(".py"):
                continue
            files += 1
            source = archive.extractfile(member).read().decode("utf-8", "replace")
            source = source.replace("\r\n", "\n")
            try:
                tree = ast.parse(source)
            except SyntaxError:
                reasons["file_not_parseable_by_python_3.11"] += 1
                continue
            lines = source.splitlines(keepends=True)
            for node in tree.body:
                if not isinstance(node, ast.FunctionDef):
                    continue
                functions += 1
                start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
                code = "".join(lines[start : node.end_lineno])
                check = guard_clauses.check_input(code)
                if not check.supported:
                    reasons.update(check.reasons)
                    continue
                if free_names(ast.parse(code).body[0]):
                    reasons["free_names"] += 1
                    continue
                target = guard_clauses.to_guard_clauses(code)
                if not guard_clauses.rubric(code, target).passed:
                    reasons["rubric_failed"] += 1
                    continue
                qualified.append(f"{member.name.split('/', 1)[1]}::{node.name}")
    result = {
        "repository": "TheAlgorithms/Python",
        "license": "MIT",
        "commit": COMMIT,
        "archive_url": URL,
        "archive_sha256": SHA256,
        "python_files": files,
        "top_level_functions": functions,
        "qualified": len(qualified),
        "qualified_functions": qualified,
        "exclusion_reasons": dict(sorted(reasons.items())),
        "note": (
            "Reasons count once per reason code; a function can have several. Parsing only; "
            "the archive's code is never executed. Not used in the dataset."
        ),
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ("python_files", "top_level_functions", "qualified")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

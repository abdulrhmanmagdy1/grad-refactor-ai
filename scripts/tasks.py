"""Cross-platform task runner: one command for every gate in the repository.

The project is developed on Windows and verified on Linux, so the usual
Makefile is not available everywhere. This script runs the same commands on
both systems and stops at the first failure:

    python scripts/tasks.py check      lint + formatting
    python scripts/tasks.py test       backend test suite
    python scripts/tasks.py docs       documentation graph
    python scripts/tasks.py dataset    curated dataset validation
    python scripts/tasks.py contract   API <-> web client drift guard
    python scripts/tasks.py smoke      release smoke test (needs frontend/dist)
    python scripts/tasks.py web        the web client gates (npm run verify)
    python scripts/tasks.py release    rebuild + verify the release manifest
    python scripts/tasks.py all        every gate above, in order
"""

import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
# On Windows npm is a .cmd shim, which subprocess cannot launch by bare name.
# Resolve it once so the same command works from PowerShell, cmd and CI.
NPM = shutil.which("npm") or "npm"


def run(*command: str, cwd: Path | None = None) -> None:
    """Run one command, streaming its output, and stop on failure."""
    print(f"\n$ {' '.join(command)}")
    started = time.perf_counter()
    result = subprocess.run(list(command), cwd=str(cwd or ROOT), check=False)
    elapsed = time.perf_counter() - started
    if result.returncode != 0:
        raise SystemExit(f"FAILED after {elapsed:.1f}s: {' '.join(command)}")
    print(f"  ok ({elapsed:.1f}s)")


def script(name: str, *args: str) -> None:
    run(PYTHON, str(ROOT / "scripts" / name), *args)


def task_check() -> None:
    run(PYTHON, "-m", "ruff", "check", ".")
    run(PYTHON, "-m", "ruff", "format", "--check", ".")


def task_release() -> None:
    script("make_release.py")
    script("verify_release.py")


TASKS: dict[str, Callable[[], None]] = {
    "check": task_check,
    "test": lambda: run(PYTHON, "-m", "pytest", "-q"),
    "docs": lambda: script("check_docs.py"),
    "dataset": lambda: script("validate_dataset.py", str(ROOT / "data" / "curated.jsonl")),
    "contract": lambda: script("check_contract.py"),
    "smoke": lambda: script("smoke_ui.py"),
    "web": lambda: run(NPM, "run", "verify", cwd=ROOT / "frontend"),
    "release": task_release,
}

ORDER = ["check", "test", "docs", "dataset", "contract", "web", "smoke", "release"]


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help", "list"):
        print(__doc__)
        return

    requested = argv[0]
    if requested != "all" and requested not in TASKS:
        raise SystemExit(f"Unknown task {requested!r}. Available: all, {', '.join(TASKS)}")

    selected = ORDER if requested == "all" else [requested]
    for name in selected:
        print(f"\n=== {name} ===")
        TASKS[name]()
    print(f"\nAll selected gates passed ({len(selected)}).")


if __name__ == "__main__":
    main(sys.argv[1:])

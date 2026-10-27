"""Score an external reviewer's findings with the project benchmark's rules (a reference arm).

    python scripts/project_benchmark_external.py --split test2 --name claude \
        --reviews path/to/folder --out path/to/run

`--reviews` holds one `<project>-review.json` per project: a list of findings with file,
line_start, line_end, category, title and explanation, written by a reviewer that saw only
the project's code (no manifest, hidden tests or reference fix). The findings are matched
to the seeded places with the same rule as the review's own, so the judge can label them
the same way. External reviewers propose no fixes here, so fix scores stay empty.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from refactor_ai.project import benchmark  # noqa: E402
from refactor_ai.project.models import Category, Finding, Severity  # noqa: E402

CATEGORIES = {c.value for c in Category}


def to_findings(items: list[dict], name: str) -> list[Finding]:
    found = []
    for number, item in enumerate(items, 1):
        category = item.get("category") if item.get("category") in CATEGORIES else "bug"
        start = item.get("line_start")
        start = int(start) if isinstance(start, int | float) and start > 0 else None
        end = item.get("line_end")
        end = int(end) if isinstance(end, int | float) and start and end >= start else start
        found.append(
            Finding(
                id=f"F{number:03d}",
                category=Category(category),
                severity=Severity.MEDIUM,
                source=f"external:{name}",
                file=str(item.get("file") or "").replace("\\", "/") or None,
                line_start=start,
                line_end=end,
                title=str(item.get("title") or "")[:120] or "(no title)",
                explanation=str(item.get("explanation") or ""),
            )
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--split", choices=benchmark.SPLITS, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    projects = benchmark.load_split(args.split, ROOT / benchmark.DATASET_ROOT)
    lines = []
    for project in projects:
        path = Path(args.reviews) / f"{project.name}-review.json"
        items = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        findings = to_findings(items, args.name)
        lines.append(
            json.dumps(
                {
                    "protocol": benchmark.PROTOCOL_ID,
                    "arm": f"external-{args.name}",
                    "project": project.name,
                    "project_sha256": project.sha256(),
                    "review_s": 0.0,
                    "summary": {},
                    "findings": [f.model_dump(mode="json") for f in findings],
                    "fixes": [],
                    "calls": [],
                    "warnings": [] if path.is_file() else [f"no review file {path.name}"],
                    "dropped": [],
                    "matching": benchmark.match_findings(findings, project.manifest),
                    "fix_scores": {"per_fix": [], "ready_together": {"resolved": []}},
                }
            )
        )
    (out / "records.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    run = {
        "protocol": benchmark.PROTOCOL_ID,
        "split": args.split,
        "arm": f"external-{args.name}",
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "frozen": False,
        "external": True,
        "git": {"commit": "", "dirty": False},
    }
    (out / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(lines)} records to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

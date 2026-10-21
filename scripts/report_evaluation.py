"""Build tables and figures from retained evaluation records (repeatable).

Usage (prefix with python -m uv run python):

    scripts/report_evaluation.py runs/evaluation/<id>/records.jsonl --out <directory>
        [--targets experiments/evaluation/protocol-freeze.json]

Writes summary.md, arm_metrics.csv, paired.csv, by_source.csv, by_source_group.csv,
by_failure_type.csv, report.json and figures/*.svg. With --targets, it also assesses the
numerical targets of that protocol freeze record (targets.csv, target_directions.csv and a
summary section). The output depends only on the records and the freeze record given.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from refactor_ai.evaluation import report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("records", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--targets", type=Path, help="protocol freeze record whose numerical targets to assess"
    )
    args = parser.parse_args(argv)
    try:
        freeze = (
            None if args.targets is None else json.loads(args.targets.read_text(encoding="utf-8"))
        )
        rows = report.load_records(args.records)
        written = report.build_report(rows, args.out, freeze=freeze)
    except (report.ReportError, OSError, ValueError) as exc:
        print(f"Cannot build the report: {exc}", file=sys.stderr)
        return 2
    for relative in sorted(written):
        print(written[relative])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

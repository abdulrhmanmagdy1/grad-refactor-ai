"""Build tables and figures from retained evaluation records (repeatable).

Usage (prefix with python -m uv run python):

    scripts/report_evaluation.py runs/evaluation/<id>/records.jsonl --out <directory>

Writes summary.md, arm_metrics.csv, paired.csv, by_source.csv, by_source_group.csv,
by_failure_type.csv, report.json and figures/*.svg. The output depends only on the records given.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from refactor_ai.evaluation import report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("records", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rows = report.load_records(args.records)
        written = report.build_report(rows, args.out)
    except report.ReportError as exc:
        print(f"Cannot build the report: {exc}", file=sys.stderr)
        return 2
    for relative in sorted(written):
        print(written[relative])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

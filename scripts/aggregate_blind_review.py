"""Summarise a filled blind-review score sheet (FR09, UC04, NFR06).

Reads the artifacts written by ``scripts/prepare_blind_review.py``:

- ``score_sheet.csv`` filled by human raters (1-5 scores per candidate),
- ``review_key.csv``  the coordinator-only candidate -> group mapping.

Computes per-group means, per-dimension standard deviations, and a simple
inter-rater spread (mean max-min range across items with two or more raters).
Writes ``review_summary.json`` next to the sheet and prints a Markdown table.

Only real human ratings are aggregated; blank or invalid rows are counted as
skipped and never imputed. If fewer than one valid rating exists, the script
exits with a clear error instead of inventing a summary.
"""

import argparse
import csv
import json
import statistics
import time
from pathlib import Path

DIMENSIONS = ("correctness_1_5", "readability_1_5", "maintainability_1_5")


def load_key(path: Path) -> dict[tuple[str, str], str]:
    """Map (case_id, candidate_label) -> producing group."""
    mapping: dict[tuple[str, str], str] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mapping[(row["case_id"], row["candidate_label"])] = row["group"]
    return mapping


def load_scores(path: Path) -> tuple[list[dict], dict[str, int], int]:
    """Return (valid rating rows, skipped-row counts by reason, total rows read)."""
    valid: list[dict] = []
    skipped = {"blank_rater": 0, "invalid_scores": 0}
    rows_total = 0
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows_total += 1
            rater = (row.get("rater") or "").strip()
            if not rater:
                skipped["blank_rater"] += 1
                continue
            scores: dict[str, int] = {}
            for dimension in DIMENSIONS:
                raw = (row.get(dimension) or "").strip()
                try:
                    value = int(raw)
                except ValueError:
                    scores = {}
                    break
                if not 1 <= value <= 5:
                    scores = {}
                    break
                scores[dimension] = value
            if not scores:
                skipped["invalid_scores"] += 1
                continue
            valid.append(
                {
                    "case_id": row["case_id"],
                    "candidate_label": row["candidate_label"],
                    "rater": rater,
                    **scores,
                }
            )
    return valid, skipped, rows_total


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 3) if values else None


def _pstdev(values: list[float]) -> float | None:
    return round(statistics.pstdev(values), 3) if len(values) >= 2 else None


def aggregate(key: dict[tuple[str, str], str], ratings: list[dict]) -> dict:
    """Pure statistics over valid ratings; ratings outside the key are counted, not used."""
    known = [r for r in ratings if (r["case_id"], r["candidate_label"]) in key]
    skipped_unknown = len(ratings) - len(known)

    by_group: dict[str, list[dict]] = {}
    for rating in known:
        by_group.setdefault(key[(rating["case_id"], rating["candidate_label"])], []).append(rating)

    group_summaries: dict[str, dict] = {}
    for group, rows in sorted(by_group.items()):
        overall_per_row = [statistics.mean(row[d] for d in DIMENSIONS) for row in rows]
        group_summaries[group] = {
            "n_ratings": len(rows),
            DIMENSIONS[0]: {
                "mean": _mean([row[DIMENSIONS[0]] for row in rows]),
                "pstdev": _pstdev([row[DIMENSIONS[0]] for row in rows]),
            },
            DIMENSIONS[1]: {
                "mean": _mean([row[DIMENSIONS[1]] for row in rows]),
                "pstdev": _pstdev([row[DIMENSIONS[1]] for row in rows]),
            },
            DIMENSIONS[2]: {
                "mean": _mean([row[DIMENSIONS[2]] for row in rows]),
                "pstdev": _pstdev([row[DIMENSIONS[2]] for row in rows]),
            },
            "overall_mean": _mean(overall_per_row),
        }

    # Inter-rater spread: per item (case, candidate) and dimension, the range
    # between the highest and lowest rating once at least two raters scored it.
    items: dict[tuple[str, str], list[dict]] = {}
    for rating in known:
        items.setdefault((rating["case_id"], rating["candidate_label"]), []).append(rating)
    multi_rater_items = {item: rows for item, rows in items.items() if len(rows) >= 2}

    dimension_ranges: dict[str, dict] = {}
    for dimension in DIMENSIONS:
        ranges = [
            max(row[dimension] for row in rows) - min(row[dimension] for row in rows)
            for rows in multi_rater_items.values()
        ]
        dimension_ranges[dimension] = {
            "items": len(ranges),
            "mean_range": _mean([float(value) for value in ranges]),
        }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raters": sorted({rating["rater"] for rating in known}),
        "rows_used": len(known),
        "skipped_unknown_pair": skipped_unknown,
        "by_group": group_summaries,
        "inter_rater": {
            "items_with_multiple_raters": len(multi_rater_items),
            "dimension_ranges": dimension_ranges,
        },
    }


def render_markdown(summary: dict) -> str:
    lines = ["# Blind review summary", ""]
    rows_used = summary["rows_used"]
    raters = ", ".join(summary["raters"]) or "—"
    lines.append(
        f"Valid ratings: {rows_used} from rater(s): {raters} of {summary['rows_total']} rows."
    )
    skipped = summary["skipped"]
    lines.append(
        "Skipped rows: " + ", ".join(f"{reason}={count}" for reason, count in skipped.items()) + "."
    )
    lines.append("")
    lines.append("| Group | n | correctness | readability | maintainability | overall |")
    lines.append("|---|---|---|---|---|---|")
    for group, stats in summary["by_group"].items():
        lines.append(
            "| `{group}` | {n} | {c} | {r} | {m} | {o} |".format(
                group=group,
                n=stats["n_ratings"],
                c=stats[DIMENSIONS[0]]["mean"],
                r=stats[DIMENSIONS[1]]["mean"],
                m=stats[DIMENSIONS[2]]["mean"],
                o=stats["overall_mean"],
            )
        )
    lines.append("")
    inter = summary["inter_rater"]
    if inter["items_with_multiple_raters"]:
        lines.append("| Dimension | items with ≥2 raters | mean max-min range |")
        lines.append("|---|---|---|")
        for dimension, stats in inter["dimension_ranges"].items():
            lines.append(f"| `{dimension}` | {stats['items']} | {stats['mean_range']} |")
    else:
        lines.append(
            "Inter-rater spread not computable yet: no item has been scored by two or more raters."
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--review-dir", type=Path, default=Path("experiments/review"))
    parser.add_argument(
        "--output", type=Path, default=None, help="Defaults to <review-dir>/review_summary.json."
    )
    args = parser.parse_args()

    key_path = args.review_dir / "review_key.csv"
    sheet_path = args.review_dir / "score_sheet.csv"
    for path in (key_path, sheet_path):
        if not path.exists():
            raise SystemExit(f"Missing {path}; run scripts/prepare_blind_review.py first.")

    key = load_key(key_path)
    ratings, skipped, rows_total = load_scores(sheet_path)
    if not ratings:
        raise SystemExit(
            "No filled ratings found in score_sheet.csv — humans have not rated yet, "
            "so there is nothing to aggregate (NFR06)."
        )

    stats = aggregate(key, ratings)
    summary = {
        "generated_at": stats["generated_at"],
        "raters": stats["raters"],
        "rows_total": rows_total,
        "rows_used": stats["rows_used"],
        "skipped": {**skipped, "unknown_pair": stats["skipped_unknown_pair"]},
        "by_group": stats["by_group"],
        "inter_rater": stats["inter_rater"],
    }
    output_path = args.output or (args.review_dir / "review_summary.json")
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(render_markdown(summary))
    print(f"Summary written to {output_path}")


if __name__ == "__main__":
    main()

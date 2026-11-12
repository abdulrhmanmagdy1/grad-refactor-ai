"""Build a blinded human-review packet from harness results (FR09, UC04, NFR06).

Reads a harness CSV that was exported with ``--include-code`` (executed rows
then carry ``original_code`` and ``refactored_code``), pairs the candidates of
every case, shuffles the candidate order deterministically per case, and
writes:

- ``packet.md``       what raters read: original code plus per-case labelled
                      candidates, with no hint of which system produced which;
- ``review_key.csv``  coordinator-only mapping from candidate label to the
                      real producing group (never share before aggregation);
- ``score_sheet.csv`` prefilled blank rating rows (one block per rater).

This script produces no scores. Humans fill the sheet, then
``scripts/aggregate_blind_review.py`` summarises the filled ratings.
"""

import argparse
import csv
import random
import time
from pathlib import Path

DIMENSIONS = ("correctness_1_5", "readability_1_5", "maintainability_1_5")
SHEET_COLUMNS = ["case_id", "candidate_label", "rater", *DIMENSIONS, "comment"]
KEY_COLUMNS = ["case_id", "candidate_label", "group", "model", "refactoring_type"]

RUBRIC = """Rate every candidate on three 1-5 scales (5 = best). Rate what you see, not what you
guess produced it:

- `correctness_1_5`    - confidence that the refactored code preserves the original behaviour;
- `readability_1_5`    - naming, structure, and clarity of the result;
- `maintainability_1_5` - how easily the result could be extended or debugged later.

Record one row per (case, candidate, rater) in `score_sheet.csv`, replacing the blank `rater`
column with your name or handle. Leave no score blank. Do not edit `packet.md` and do not open
`review_key.csv`: candidate labels are randomised per case and the key would break the blind
protocol."""


def _fence(code: str, language: str = "python") -> str:
    """Wrap code in a fence long enough to survive embedded backticks."""
    longest = 0
    current = 0
    for char in code:
        current = current + 1 if char == "`" else 0
        longest = max(longest, current)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{language}\n{code.rstrip()}\n{ticks}"


def load_executed_records(path: Path) -> dict[str, list[dict]]:
    """Group executed rows carrying candidate code by case id."""
    groups: dict[str, list[dict]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "executed":
                continue
            if not (row.get("refactored_code") or "").strip():
                continue
            groups.setdefault(row["case_id"], []).append(row)
    return groups


def build_review(
    records_by_case: dict[str, list[dict]],
    seed: str = "20261019",
    raters_per_candidate: int = 5,
    generated_at: str | None = None,
) -> tuple[str, list[dict], list[dict]]:
    """Return ``(packet_markdown, key_rows, sheet_rows)``.

    Candidate order is shuffled with ``random.Random(f"{seed}:{case_id}")``,
    which is deterministic across processes and platforms. Pass
    ``generated_at`` to reproduce a packet byte-for-byte; by default the
    current UTC time is recorded in the footer.
    """
    eligible = {case: rows for case, rows in records_by_case.items() if len(rows) >= 2}
    if not eligible:
        raise SystemExit(
            "No case has at least two executed candidates with code. "
            "Re-export the results with: python -m evaluation.harness ... --include-code"
        )

    packet_parts = [
        "# Blinded refactoring review packet",
        "This packet compares alternative refactorings of the same input. "
        "Every candidate is shown without its producing system; labels are randomised per case.",
        RUBRIC,
    ]
    key_rows: list[dict] = []
    sheet_rows: list[dict] = []

    for case_id in sorted(eligible):
        rows = sorted(eligible[case_id], key=lambda row: row["group"])
        order = list(range(len(rows)))
        random.Random(f"{seed}:{case_id}").shuffle(order)

        section = [
            f"## `{case_id}`",
            f"Refactoring type: `{rows[0].get('refactoring_type', 'general')}`",
        ]
        section.append("### Original code")
        section.append(_fence(rows[0]["original_code"]))
        for display_index, row_index in enumerate(order, start=1):
            row = rows[row_index]
            label = f"Candidate {display_index}"
            section.append(f"### {label}")
            section.append(_fence(row["refactored_code"]))
            key_rows.append(
                {
                    "case_id": case_id,
                    "candidate_label": label,
                    "group": row["group"],
                    "model": row.get("model", ""),
                    "refactoring_type": row.get("refactoring_type", ""),
                }
            )
            for _ in range(raters_per_candidate):
                sheet_rows.append(
                    {
                        "case_id": case_id,
                        "candidate_label": label,
                        "rater": "",
                        **{dimension: "" for dimension in DIMENSIONS},
                        "comment": "",
                    }
                )
        packet_parts.append("\n\n".join(section))

    generated_at = generated_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    packet_parts.append(
        f"_Generated at {generated_at} from {len(eligible)} blinded cases. "
        "Scores are recorded only by the human raters in `score_sheet.csv`._"
    )
    return "\n\n".join(packet_parts) + "\n", key_rows, sheet_rows


def write_outputs(
    out_dir: Path,
    packet: str,
    key_rows: list[dict],
    sheet_rows: list[dict],
    force: bool = False,
) -> tuple[Path, Path, Path]:
    """Write the three packet files, refusing to clobber existing work by default."""
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_path = out_dir / "packet.md"
    key_path = out_dir / "review_key.csv"
    sheet_path = out_dir / "score_sheet.csv"

    existing = [path.name for path in (packet_path, key_path, sheet_path) if path.exists()]
    if existing and not force:
        raise SystemExit(
            f"Refusing to overwrite existing review artifacts: {', '.join(existing)}. "
            "Pass --force to regenerate (this deletes any filled score sheet)."
        )

    packet_path.write_text(packet, encoding="utf-8")
    for path, rows, columns in (
        (key_path, key_rows, KEY_COLUMNS),
        (sheet_path, sheet_rows, SHEET_COLUMNS),
    ):
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    return packet_path, key_path, sheet_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("experiments/dataset_test_results.csv"),
        help="Harness CSV exported with --include-code.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/review"))
    parser.add_argument(
        "--seed",
        type=str,
        default="20261019",
        help="Blinding seed; reuse the same seed and results to reproduce the exact packet.",
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help=(
            "Fixed UTC timestamp for the packet footer; pass the original value to "
            "reproduce a packet byte-for-byte (defaults to now)."
        ),
    )
    parser.add_argument("--raters-per-candidate", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    records = load_executed_records(args.results)
    packet, key_rows, sheet_rows = build_review(
        records,
        seed=args.seed,
        raters_per_candidate=args.raters_per_candidate,
        generated_at=args.generated_at,
    )
    packet_path, key_path, sheet_path = write_outputs(
        args.output_dir, packet, key_rows, sheet_rows, force=args.force
    )
    print(f"Blinded packet:  {packet_path}")
    print(f"Coordinator key: {key_path} (do not share before aggregation)")
    print(f"Blank sheet:     {sheet_path} ({len(sheet_rows)} rating rows)")


if __name__ == "__main__":
    main()

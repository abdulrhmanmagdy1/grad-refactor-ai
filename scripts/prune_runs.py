"""Retention for the local run history: delete the oldest runs beyond a window.

A single-machine installation keeps every run forever otherwise, and the local
SQLite file is also the audit trail. So the script is a *dry run* unless
``--yes`` is passed, always keeps the most recent ``--keep`` records, and prints
exactly what it would remove.

Usage:
    python scripts/prune_runs.py --keep 500            # show what would go
    python scripts/prune_runs.py --keep 500 --yes      # delete it
    python scripts/prune_runs.py --keep 500 --yes --vacuum
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prune(database: Path, keep: int, apply: bool = False, vacuum: bool = False) -> dict:
    """Return the retention report, deleting the oldest runs only when ``apply``."""
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        total = int(connection.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"])
        if total <= keep:
            return {
                "total": total,
                "keep": keep,
                "deleted": 0,
                "would_delete": 0,
                "kept": total,
                "ids": [],
            }

        rows = connection.execute(
            "SELECT id FROM runs ORDER BY created_at DESC, id DESC LIMIT -1 OFFSET ?",
            (keep,),
        ).fetchall()
        ids = [row["id"] for row in rows]

        if apply and ids:
            placeholders = ",".join("?" for _ in ids)
            connection.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", ids)
            connection.commit()
            if vacuum:
                connection.execute("VACUUM")
    finally:
        connection.close()

    return {
        "total": total,
        "keep": keep,
        "deleted": len(ids) if apply else 0,
        "would_delete": len(ids),
        "kept": total - len(ids),
        "ids": ids,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / "runs.sqlite3",
        help="SQLite file holding the run history (default: runs.sqlite3).",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=500,
        help="Number of most-recent runs to keep (default: 500).",
    )
    parser.add_argument("--yes", action="store_true", help="Actually delete; without it, dry run.")
    parser.add_argument("--vacuum", action="store_true", help="Compact the file after deleting.")
    parser.add_argument("--show-ids", action="store_true", help="Print the affected run ids.")
    args = parser.parse_args(argv)

    if args.keep < 1:
        parser.error("--keep must be at least 1")
    if not args.db.exists():
        print(f"No database at {args.db}; nothing to prune.")
        return 0

    report = prune(args.db, args.keep, apply=args.yes, vacuum=args.vacuum)
    if report["total"] <= report["keep"]:
        window = report["keep"]
        print(f"{report['total']} run(s) stored; the retention window is {window}. Nothing to do.")
        return 0

    verb = "Deleted" if args.yes else "Would delete"
    print(
        f"{verb} {report['would_delete']} of {report['total']} run(s); "
        f"keeping the most recent {report['keep']} ({report['kept']} remain)."
    )
    if args.show_ids:
        for run_id in report["ids"]:
            print(f"  {run_id}")
    if not args.yes:
        print("Dry run only. Re-run with --yes to delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Writing election results to the results folder."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from voting.counting import RunoffResult
from voting.quorum import QuorumReport


def slugify(name: str) -> str:
    """Turn an election name into a file name stem: lower case letters, digits, dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "election"


def export_results(
    results_dir: Path, election_name: str, quorum: QuorumReport, result: RunoffResult | None
) -> Path:
    """Write the result files inside ``results_dir`` and return the JSON file's path.

    ``<slug>.json`` holds the whole result and ``<slug>-rounds.csv`` one row per
    candidate and round. The folder is created if missing, and the files never land
    outside it whatever the election is called. ``result`` is None when the quorum was
    not met and nothing was counted.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(election_name)
    rounds = result.rounds if result else []
    summary = {
        "election": election_name,
        "quorum": {"eligible": quorum.eligible, "required": quorum.required,
                   "cast": quorum.cast, "met": quorum.met},
        "winner": result.winner if result else None,
        "rounds": rounds,
        "eliminated": result.eliminated if result else [],
        "exhausted": result.exhausted if result else 0,
    }
    json_path = results_dir / f"{stem}.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (results_dir / f"{stem}-rounds.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["round", "candidate", "votes"])
        for number, tallies in enumerate(rounds, start=1):
            for candidate, votes in sorted(tallies.items()):
                writer.writerow([number, candidate, votes])
    return json_path

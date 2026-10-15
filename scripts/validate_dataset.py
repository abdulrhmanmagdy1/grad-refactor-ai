"""Validate JSONL fields, exact normalized duplicates, and source-group separation."""

import argparse
import hashlib
import json
from pathlib import Path

REQUIRED = ("id", "source_group", "split", "prompt", "completion", "license", "refactoring_type")


def load_and_validate(path: Path) -> list[dict]:
    records = []
    ids = set()
    groups = {}
    prompts = set()
    completions = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Line {number}: expected an object")
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in REQUIRED):
            raise ValueError(f"Line {number}: missing or blank required string")
        if row["split"] not in {"train", "validation", "test"}:
            raise ValueError(f"Line {number}: invalid split")
        if row["id"] in ids:
            raise ValueError(f"Line {number}: duplicate id")
        ids.add(row["id"])
        group, split = row["source_group"], row["split"]
        if groups.setdefault(group, split) != split:
            raise ValueError(f"Line {number}: source_group crosses splits")
        prompt = hashlib.sha256(" ".join(row["prompt"].split()).encode()).hexdigest()
        if prompt in prompts:
            raise ValueError(f"Line {number}: duplicate normalized prompt")
        prompts.add(prompt)
        completion = hashlib.sha256(" ".join(row["completion"].split()).encode()).hexdigest()
        if completions.setdefault(completion, split) != split:
            raise ValueError(f"Line {number}: completion crosses splits")
        records.append(row)
    if not records:
        raise ValueError("Dataset is empty")
    if not {"train", "validation", "test"}.issubset({r["split"] for r in records}):
        raise ValueError("Expected non-empty train, validation and test splits")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    rows = load_and_validate(parser.parse_args().path)
    print(
        json.dumps(
            {
                "records": len(rows),
                "splits": {
                    s: sum(r["split"] == s for r in rows) for s in ("train", "validation", "test")
                },
            },
            indent=2,
        )
    )

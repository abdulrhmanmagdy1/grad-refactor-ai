"""Dataset records as trusted reference cases for the evaluation harness."""

from __future__ import annotations

import hashlib
from pathlib import Path

from refactor_ai.contracts import ReferenceCase, ReferenceTest
from refactor_ai.evaluation.records import read_jsonl

DEFAULT_DATASET = Path("datasets/guard_clauses/v1/records.jsonl")


def load_records(path: Path) -> list[dict]:
    return read_jsonl(path)


def dataset_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select(records: list[dict], split: str, case_ids: list[str] | None = None) -> list[dict]:
    """Records of one split in file order, optionally restricted to given ids."""
    chosen = [record for record in records if record["split"] == split]
    if case_ids:
        wanted = set(case_ids)
        missing = wanted - {record["id"] for record in chosen}
        if missing:
            raise ValueError(f"case ids not in the {split} split: {sorted(missing)}")
        chosen = [record for record in chosen if record["id"] in wanted]
    return chosen


def to_reference_case(record: dict) -> ReferenceCase:
    """The record's trusted tests as a ReferenceCase; the case id is the record id."""
    return ReferenceCase(
        case_id=record["id"],
        task_type=record["refactoring_type"],
        title=None,
        function_name=record["function_name"],
        original_code=record["original_code"],
        reference_code=record["target_code"],
        tests=[ReferenceTest.model_validate(test) for test in record["tests"]],
        source_group=record["source_group"],
        license=record["license"],
        provenance=record["provenance"],
    )

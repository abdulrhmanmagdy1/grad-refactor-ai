import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "validator", Path(__file__).resolve().parents[1] / "scripts" / "validate_dataset.py"
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def dataset(tmp_path, rows):
    file = tmp_path / "records.jsonl"
    file.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return file


def sample():
    return [
        {
            "id": str(i),
            "source_group": f"repo-{i}",
            "split": split,
            "prompt": f"input-{i}",
            "completion": f"output-{i}",
            "license": "CC0-1.0",
            "refactoring_type": "fixture",
        }
        for i, split in enumerate(("train", "validation", "test"))
    ]


def test_valid_dataset(tmp_path):
    assert len(validator.load_and_validate(dataset(tmp_path, sample()))) == 3


def test_rejects_cross_split_source(tmp_path):
    rows = sample()
    rows[1]["source_group"] = rows[0]["source_group"]
    with pytest.raises(ValueError, match="crosses splits"):
        validator.load_and_validate(dataset(tmp_path, rows))


def test_rejects_duplicate_prompt(tmp_path):
    rows = sample()
    rows[1]["prompt"] = rows[0]["prompt"] + "  "
    with pytest.raises(ValueError, match="duplicate normalized prompt"):
        validator.load_and_validate(dataset(tmp_path, rows))


def test_rejects_empty_missing_split_and_target_leakage(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        validator.load_and_validate(dataset(tmp_path, []))
    with pytest.raises(ValueError, match="non-empty"):
        validator.load_and_validate(dataset(tmp_path, sample()[:2]))
    rows = sample()
    rows[2]["completion"] = rows[0]["completion"]
    with pytest.raises(ValueError, match="completion crosses"):
        validator.load_and_validate(dataset(tmp_path, rows))

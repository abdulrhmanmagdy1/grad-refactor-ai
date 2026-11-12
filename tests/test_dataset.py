import importlib.util
import json
from collections import Counter
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


def test_curated_dataset_has_balanced_clean_controls():
    path = Path(__file__).resolve().parents[1] / "data" / "curated.jsonl"
    rows = validator.load_and_validate(path)

    assert len(rows) == 416
    split_counts = {
        split: sum(row["split"] == split for row in rows)
        for split in ("train", "validation", "test")
    }
    assert split_counts == {"train": 320, "validation": 48, "test": 48}

    # The training renderer must see exactly the code inference sees: no
    # provenance comment inside the prompt.
    assert all("# example:" not in row["prompt"] for row in rows)
    assert all("# example:" not in row["completion"] for row in rows)

    findings = [row for row in rows if row["variant"] == "findings"]
    clean = [row for row in rows if row["variant"] == "clean-control"]
    assert len(findings) == 224
    assert len(clean) == 192
    assert all(row["smell_rule"] for row in findings)
    assert all(row["smell_rule"] is None for row in clean)
    assert all(row["prompt"] == row["completion"] for row in clean)
    assert all(row["prompt"] != row["completion"] for row in findings)

    counts = Counter((row["refactoring_type"], row["split"], row["variant"]) for row in rows)
    for refactoring_type in {row["refactoring_type"] for row in rows}:
        assert counts[(refactoring_type, "train", "findings")] == 20
        assert counts[(refactoring_type, "train", "clean-control")] == 20
        assert counts[(refactoring_type, "validation", "findings")] == 4
        assert counts[(refactoring_type, "validation", "clean-control")] == 2
        assert counts[(refactoring_type, "test", "findings")] == 4
        assert counts[(refactoring_type, "test", "clean-control")] == 2


def test_curated_dataset_files_use_lf_line_endings():
    root = Path(__file__).resolve().parents[1]
    for rel in ("data/curated.jsonl", "data/manifest.json"):
        raw = (root / rel).read_bytes()
        assert b"\r\n" not in raw, f"{rel} must use LF line endings to match data/manifest.json"

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


# --- Extended (optional) checks of the dataset-record contract --------------------------

FUNCTIONS = {
    "train": "def f(x):\n    if x > 0:\n        if x > 9:\n            return 9\n"
    "        else:\n            return x\n    else:\n        raise ValueError('neg')\n",
    "validation": "def g(name):\n    if name:\n        if name == 'a':\n            return 1\n"
    "        return 2\n    else:\n        return None\n",
    "test": "def h(n, limit=3):\n    if n is not None:\n        if n < limit:\n"
    "            return 'low'\n        else:\n            return 'high'\n    else:\n"
    "        raise TypeError('n')\n",
}


def contract_rows():
    from refactor_ai import task_format
    from refactor_ai.tasks import guard_clauses

    rows = []
    for split, code in FUNCTIONS.items():
        target = guard_clauses.to_guard_clauses(code)
        rows.append(
            {
                "id": f"gc1-{split}-01",
                "source_group": f"tpl-{split}",
                "split": split,
                "prompt": task_format.build_refactor_user_prompt(code),
                "completion": task_format.render_refactor_completion("Uses guard clauses.", target),
                "license": "LicenseRef-team-authored-pending",
                "refactoring_type": "guard_clauses",
                "original_code": code,
                "target_code": target,
                "function_name": guard_clauses.check_input(code).function_name,
                "tests": [
                    {
                        "args": "[None]",
                        "kwargs": "{}",
                        "expect": {"kind": "raise", "value": None, "exception": "TypeError"},
                    }
                ],
                "source": "team-template",
                "source_url": "repo:tests",
                "provenance": "test fixture",
                "prompt_version": task_format.PROMPT_VERSION,
                "task_version": guard_clauses.TASK_VERSION,
            }
        )
    return rows


def test_extended_checks_accept_contract_records(tmp_path):
    rows = contract_rows()
    assert len(validator.load_and_validate(dataset(tmp_path, rows))) == 3
    summary = validator.validate_extended(rows)
    assert summary["records_checked"] == 3 and summary["cross_split_pairs_examined"] > 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("target_code", "def f(x):\n    return x\n", "not the reference transformation"),
        ("prompt", "Task: guard_clauses\nCode:\n```python\ndef f(x): pass\n```", "prompt is not"),
        ("completion", "no code here", "completion does not parse"),
        ("tests", [], "non-empty list"),
        ("tests", [{"args": "[1", "kwargs": "{}", "expect": {"kind": "return"}}], "invalid"),
        ("function_name", "other", "function_name does not match"),
        ("prompt_version", "refactor-v0", "prompt_version"),
        ("id", "Has Spaces", "valid reference case id"),
    ],
)
def test_extended_checks_report_contract_violations(field, value, message):
    rows = contract_rows()
    rows[0][field] = value
    with pytest.raises(ValueError, match=message):
        validator.validate_extended(rows, near_duplicates=False)


def test_extended_checks_flag_cross_split_near_duplicates():
    rows = contract_rows()
    rows[1] = dict(rows[0], id="gc1-copy-01", split="validation", source_group="tpl-copy")
    with pytest.raises(ValueError, match="near-duplicate across splits"):
        validator.validate_extended(rows)


def test_extended_checks_flag_external_fixtures(tmp_path):
    rows = contract_rows()
    (tmp_path / "pilot.py").write_text(f"CODE = '''{FUNCTIONS['test']}'''\n", encoding="utf-8")
    with pytest.raises(ValueError, match="near-duplicates external"):
        validator.validate_extended(rows, near_duplicates=False, external=[tmp_path], root=tmp_path)

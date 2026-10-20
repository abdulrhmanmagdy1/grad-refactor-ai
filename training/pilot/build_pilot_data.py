"""Build the LoRA pilot JSONL (PILOT MATERIAL, not the curated dataset).

Run from the repository root with either environment (standard library only):

    python training/pilot/build_pilot_data.py

Every lora_pilot function in functions.py must pass guard_clauses.check_input. The
target is guard_clauses.to_guard_clauses() and the completion is
task_format.render_refactor_completion(), so the records have exactly the validator's
format (scripts/validate_dataset.py) plus the dataset fields from the contracts. The
output is deterministic; its SHA-256 is printed and recorded with each pilot run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from functions import PILOT_LICENSE, PILOT_SOURCE, pilot_functions  # noqa: E402

from refactor_ai import task_format  # noqa: E402
from refactor_ai.tasks import guard_clauses  # noqa: E402

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "pilot-records.jsonl"
PROVENANCE = (
    "Pilot record for the T05 LoRA feasibility run. Function written for this pilot by the "
    "models workstream on 2026-10-20; target produced by guard_clauses.to_guard_clauses and "
    "rendered by task_format.render_refactor_completion. Not part of datasets/."
)


def load_validator():
    path = ROOT / "scripts" / "validate_dataset.py"
    spec = importlib.util.spec_from_file_location("validate_dataset", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_records() -> list[dict]:
    records = []
    for item in pilot_functions("lora_pilot"):
        code = item["code"]
        check = guard_clauses.check_input(code)
        if not check.supported:
            raise SystemExit(f"{item['id']} is outside the task scope: {check.reasons}")
        target = guard_clauses.to_guard_clauses(code)
        rubric = guard_clauses.rubric(code, target)
        if not rubric.passed:
            raise SystemExit(f"{item['id']}: the reference target fails the rubric")
        after = guard_clauses.code_nesting_depth(target)
        explanation = (
            "Handled the special cases first with early returns or raises, which lowers the "
            f"nesting depth from {check.nesting_depth} to {after}."
        )
        records.append(
            {
                "id": item["id"],
                "source_group": f"pilot/{item['id']}",
                "split": item["split"],
                "prompt": task_format.build_refactor_user_prompt(code),
                "completion": task_format.render_refactor_completion(explanation, target),
                "license": PILOT_LICENSE,
                "refactoring_type": guard_clauses.TASK_TYPE,
                "original_code": code,
                "target_code": target,
                "function_name": check.function_name,
                "tests": [],
                "source": PILOT_SOURCE,
                "source_url": None,
                "provenance": PROVENANCE,
                "prompt_version": task_format.PROMPT_VERSION,
                "task_version": guard_clauses.TASK_VERSION,
                "label": "pilot",
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    records = build_records()
    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    rows = load_validator().load_and_validate(args.output)
    splits = {
        name: sum(r["split"] == name for r in rows) for name in ("train", "validation", "test")
    }
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(args.output.name), "splits": splits, "sha256": digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Writing the curated dataset, its manifest, the curation log and the test-split freeze.

Hashes are SHA-256 over UTF-8 bytes with LF line endings. A split hash covers that
split's JSON lines exactly as they appear in records.jsonl, in file order, each followed
by LF, so it can be recomputed from the records file alone (see split_sha256). Git may
check text files out with CRLF on Windows; verification normalizes CRLF to LF first.

Every output except the run record is a pure function of the curation code, the seed
and the pinned inputs, so rerunning the command reproduces them byte for byte. The test
split is frozen explicitly (--freeze-test); afterwards any run that would change the
frozen test split fails before writing anything.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter
from pathlib import Path

from refactor_ai.data.curate import DATASET_VERSION, CurationConfig, CurationResult
from refactor_ai.data.sources import SOURCES
from refactor_ai.data.splits import SPLITS
from refactor_ai.task_format import PROMPT_VERSION
from refactor_ai.tasks import guard_clauses

FREEZE_DATE = "2026-10-20"
DATASET_DIR = Path("datasets/guard_clauses/v1")
LOG_DIR = Path("experiments/data")
DEMO_PATH = Path("src/refactor_ai/fixtures/demo_cases.json")
RECORDS_NAME = "records.jsonl"
METADATA_NAME = "metadata.jsonl"
MANIFEST_NAME = "manifest.json"
LOG_NAME = "curation-log.json"
RUN_NAME = "curation-run.json"
FREEZE_NAME = "test-split-freeze.json"
COMMAND = "python -m uv run python scripts/curate_dataset.py"
HASH_METHOD = (
    "SHA-256 of UTF-8 bytes with LF line endings (normalize CRLF to LF before hashing). "
    "A split hash covers that split's JSON lines from records.jsonl in file order, each "
    "followed by LF."
)
CURATION_SOURCES = (
    "scripts/curate_dataset.py",
    "src/refactor_ai/data/__init__.py",
    "src/refactor_ai/data/_harness.py",
    "src/refactor_ai/data/codegen.py",
    "src/refactor_ai/data/curate.py",
    "src/refactor_ai/data/demo.py",
    "src/refactor_ai/data/executor.py",
    "src/refactor_ai/data/explain.py",
    "src/refactor_ai/data/leakage.py",
    "src/refactor_ai/data/manifest.py",
    "src/refactor_ai/data/mutation.py",
    "src/refactor_ai/data/refgen.py",
    "src/refactor_ai/data/sources.py",
    "src/refactor_ai/data/splits.py",
    "src/refactor_ai/data/families/__init__.py",
    "src/refactor_ai/data/families/access.py",
    "src/refactor_ai/data/families/base.py",
    "src/refactor_ai/data/families/commerce.py",
    "src/refactor_ai/data/families/finance.py",
    "src/refactor_ai/data/families/helpers.py",
    "src/refactor_ai/data/families/logistics.py",
    "src/refactor_ai/data/families/people.py",
    "src/refactor_ai/data/families/systems.py",
    "src/refactor_ai/data/families/text.py",
    "src/refactor_ai/tasks/guard_clauses.py",
    "src/refactor_ai/task_format.py",
)
FREEZE_RULE = (
    "Frozen held-out test split. Use it only for the final A/B/C/D run under a frozen "
    "evaluation protocol. Do not train, tune prompts, select models or hyperparameters, or "
    "set targets on it. Any change to these records requires a new dataset version and a "
    "new protocol version."
)


class FrozenSplitChanged(RuntimeError):
    """The curation would change a test split that has already been frozen."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def record_line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=True)


def jsonl_text(rows: list[dict]) -> str:
    return "".join(record_line(row) + "\n" for row in rows)


def split_sha256(records_text: str, split: str) -> str:
    """Hash of one split, recomputed from the text of records.jsonl."""
    lines = [
        line
        for line in records_text.replace("\r\n", "\n").split("\n")
        if line.strip() and json.loads(line)["split"] == split
    ]
    return sha256_text("".join(line + "\n" for line in lines))


def pretty_json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True) + "\n"


def _counts(records: list[dict]) -> dict:
    def tally(key) -> dict:
        return dict(sorted(Counter(key(r) for r in records).items()))

    return {
        "total": len(records),
        "by_split": {split: sum(r["split"] == split for r in records) for split in SPLITS},
        "by_source": tally(lambda r: r["source"]),
        "by_license": tally(lambda r: r["license"]),
        "by_split_and_source": {
            split: dict(
                sorted(Counter(r["source"] for r in records if r["split"] == split).items())
            )
            for split in SPLITS
        },
        "source_groups_by_split": {
            split: len({r["source_group"] for r in records if r["split"] == split})
            for split in SPLITS
        },
        "tests_total": sum(len(r["tests"]) for r in records),
    }


def _metric_summary(metadata: list[dict]) -> dict:
    def ratio(numerator: str, denominator: str) -> dict:
        num = sum(m["test_metrics"][numerator] for m in metadata)
        den = sum(m["test_metrics"][denominator] for m in metadata)
        return {"numerator": num, "denominator": den, "ratio": round(num / den, 4) if den else None}

    tests = sorted(m["test_metrics"]["tests"] for m in metadata)
    return {
        "records": len(metadata),
        "tests_per_record": {"min": tests[0], "max": tests[-1], "total": sum(tests)}
        if tests
        else None,
        "exit_lines_covered": ratio("exit_lines_covered", "exit_lines"),
        "branch_outcomes_covered_of_total": ratio(
            "branch_outcomes_covered", "branch_outcomes_total"
        ),
        "branch_outcomes_covered_of_reachable": ratio(
            "branch_outcomes_covered", "branch_outcomes_reachable"
        ),
        "mutants_killed_of_killable": ratio("mutants_killed", "mutants_killable"),
        "mutants_killed_of_all": ratio("mutants_killed", "mutants"),
        "records_with_findings_notes": sum(bool(m["prompt_has_findings"]) for m in metadata),
    }


def _exclusion_summary(log: dict) -> dict:
    counter = Counter(f"{e['stage']}:{e['reason']}" for e in log["exclusions"])
    return dict(sorted(counter.items()))


def _demo_file_entry(root: Path) -> dict:
    path = root / DEMO_PATH
    if not path.exists():
        return {"path": DEMO_PATH.as_posix(), "sha256": None, "cases": 0}
    text = path.read_text(encoding="utf-8")
    return {
        "path": DEMO_PATH.as_posix(),
        "sha256": sha256_text(text),
        "cases": len(json.loads(text)),
        "independence": "checked against every split by the near-duplicate rule (see curation log)",
    }


def source_hashes(root: Path) -> dict[str, str]:
    hashes = {}
    for relative in CURATION_SOURCES:
        path = root / relative
        if path.exists():
            hashes[relative] = sha256_text(path.read_text(encoding="utf-8"))
    return hashes


def build_manifest(
    result: CurationResult, records_text: str, metadata_text: str, log_text: str, root: Path
) -> dict:
    records = result.records
    splits = {}
    for split in SPLITS:
        rows = [r for r in records if r["split"] == split]
        splits[split] = {
            "count": len(rows),
            "sha256": split_sha256(records_text, split),
            "source_groups": sorted({r["source_group"] for r in rows}),
            "ids": [r["id"] for r in rows],
        }
    sources = [
        {
            "source": "team-template",
            "license": "LicenseRef-team-authored-pending",
            "note": (
                "Template families written for this project by the coding agent on behalf of "
                "the team (src/refactor_ai/data/families/). Redistribution license pending a "
                "team decision."
            ),
        }
    ]
    for name in sorted(SOURCES):
        src = SOURCES[name]
        sources.append(
            {
                "source": name,
                "license": src.license,
                "license_url": src.license_url,
                "download_url": src.url,
                "download_sha256": src.sha256,
                "citation": src.citation,
            }
        )
    return {
        "dataset": DATASET_VERSION,
        "task": {
            "type": guard_clauses.TASK_TYPE,
            "task_version": guard_clauses.TASK_VERSION,
            "prompt_version": PROMPT_VERSION,
        },
        "command": COMMAND,
        "seed": result.config_summary["seed"],
        "hash_method": HASH_METHOD,
        "files": {
            "records": {
                "path": (DATASET_DIR / RECORDS_NAME).as_posix(),
                "sha256": sha256_text(records_text),
                "lines": len(records),
                "bytes_lf": len(records_text.encode("utf-8")),
            },
            "metadata": {
                "path": (DATASET_DIR / METADATA_NAME).as_posix(),
                "sha256": sha256_text(metadata_text),
            },
            "curation_log": {
                "path": (LOG_DIR / LOG_NAME).as_posix(),
                "sha256": sha256_text(log_text),
            },
            "demo_cases": _demo_file_entry(root),
        },
        "counts": _counts(records),
        "splits": splits,
        "sources": sources,
        "test_metrics": _metric_summary(result.metadata),
        "exclusions_by_stage_and_reason": _exclusion_summary(result.log),
        "generation": result.config_summary,
        "code_sha256": source_hashes(root),
    }


def freeze_record(manifest: dict, git_head: str | None) -> dict:
    test = manifest["splits"]["test"]
    return {
        "dataset": manifest["dataset"],
        "records_path": manifest["files"]["records"]["path"],
        "split": "test",
        "frozen_on": FREEZE_DATE,
        "count": test["count"],
        "split_sha256": test["sha256"],
        "hash_method": HASH_METHOD,
        "ids": test["ids"],
        "source_groups": test["source_groups"],
        "rule": FREEZE_RULE,
        "frozen_by": (
            "data and evaluation workstream (coding agent working for Shahd Abdelhay); "
            "pending the owner's inspection"
        ),
        "curation_command": COMMAND,
        "curation_seed": manifest["seed"],
        "git_head_at_freeze": git_head,
        "code_sha256_at_freeze": manifest["code_sha256"],
    }


def git_head(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() or None


def uncommitted(root: Path, paths: tuple[str, ...]) -> list[str] | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", *paths],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return sorted(line[3:] for line in completed.stdout.splitlines() if line.strip())


def render_outputs(result: CurationResult, root: Path) -> dict[str, str]:
    """All deterministic output files as text, keyed by repository-relative path."""
    records_text = jsonl_text(result.records)
    metadata_text = jsonl_text(result.metadata)
    log_text = pretty_json(result.log)
    manifest = build_manifest(result, records_text, metadata_text, log_text, root)
    return {
        (DATASET_DIR / RECORDS_NAME).as_posix(): records_text,
        (DATASET_DIR / METADATA_NAME).as_posix(): metadata_text,
        (DATASET_DIR / MANIFEST_NAME).as_posix(): pretty_json(manifest),
        (LOG_DIR / LOG_NAME).as_posix(): log_text,
    }


def check_freeze(outputs: dict[str, str], root: Path) -> dict | None:
    """Return the existing freeze record, raising if the new test split differs from it."""
    path = root / LOG_DIR / FREEZE_NAME
    if not path.exists():
        return None
    frozen = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads(outputs[(DATASET_DIR / MANIFEST_NAME).as_posix()])
    test = manifest["splits"]["test"]
    if test["sha256"] != frozen["split_sha256"] or test["ids"] != frozen["ids"]:
        raise FrozenSplitChanged(
            "The curated test split differs from the frozen split "
            f"({test['sha256']} != {frozen['split_sha256']}). A frozen test split may only "
            "change with a new dataset version and a new evaluation protocol version."
        )
    return frozen


def write_outputs(
    result: CurationResult, config: CurationConfig, *, freeze_test: bool
) -> dict[str, str]:
    """Write all outputs; returns path -> sha256. Refuses to change a frozen test split."""
    root = config.root
    outputs = render_outputs(result, root)
    frozen = check_freeze(outputs, root)
    manifest = json.loads(outputs[(DATASET_DIR / MANIFEST_NAME).as_posix()])
    head = git_head(root)
    written = {}
    for relative, text in outputs.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written[relative] = sha256_text(text)
    freeze_path = root / LOG_DIR / FREEZE_NAME
    if frozen is None and freeze_test:
        frozen = freeze_record(manifest, head)
        freeze_path.write_text(pretty_json(frozen), encoding="utf-8", newline="\n")
    if freeze_path.exists():
        written[(LOG_DIR / FREEZE_NAME).as_posix()] = sha256_text(
            freeze_path.read_text(encoding="utf-8")
        )
    run = {
        "command": COMMAND,
        "seed": result.config_summary["seed"],
        "git_head": head,
        "uncommitted_curation_sources": uncommitted(root, CURATION_SOURCES),
        "python": platform.python_version(),
        "implementation": sys.implementation.name,
        "platform": platform.system(),
        "test_split_frozen": frozen is not None,
        "outputs_sha256": dict(sorted(written.items())),
        "note": (
            "Run record. Every output listed above is reproduced byte for byte by rerunning "
            "the command with the same inputs; this run record is not."
        ),
    }
    run_path = root / LOG_DIR / RUN_NAME
    run_path.write_text(pretty_json(run), encoding="utf-8", newline="\n")
    return written

"""The committed dataset, its manifest, the frozen test split and the demonstration cases."""

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from refactor_ai.contracts import ReferenceCase
from refactor_ai.data import leakage
from refactor_ai.data.demo import build_demo_cases, demo_cases_json
from refactor_ai.data.executor import Job, run_jobs
from refactor_ai.tasks import guard_clauses as gc

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "datasets" / "guard_clauses" / "v1" / "records.jsonl"
MANIFEST = ROOT / "datasets" / "guard_clauses" / "v1" / "manifest.json"
FREEZE = ROOT / "experiments" / "data" / "test-split-freeze.json"
DEMO = ROOT / "src" / "refactor_ai" / "fixtures" / "demo_cases.json"
PILOT = ROOT / "training" / "pilot"

spec = importlib.util.spec_from_file_location("validator", ROOT / "scripts" / "validate_dataset.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


@pytest.fixture(scope="module")
def rows():
    return validator.load_and_validate(RECORDS)


def test_dataset_passes_basic_and_extended_validation(rows):
    summary = validator.validate_extended(rows)
    assert summary["records_checked"] == len(rows)
    assert summary["cross_split_pairs_examined"] > 0


def test_manifest_matches_the_records(rows):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert validator.verify_manifest(RECORDS, MANIFEST) == []
    assert manifest["counts"]["total"] == len(rows)
    for split in ("train", "validation", "test"):
        assert manifest["counts"]["by_split"][split] == sum(r["split"] == split for r in rows)
    assert manifest["files"]["records"]["sha256"] == validator.file_sha256(RECORDS)


def test_test_split_is_frozen():
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert frozen["frozen_on"] == "2026-10-20" and frozen["split"] == "test"
    assert validator.verify_freeze(RECORDS, FREEZE) == []
    assert frozen["split_sha256"] == manifest["splits"]["test"]["sha256"]
    assert frozen["ids"] == manifest["splits"]["test"]["ids"]


def test_reference_tests_hold_for_original_and_target(rows):
    jobs = []
    for row in rows:
        calls = tuple((t["args"], t["kwargs"]) for t in row["tests"])
        jobs.append(Job(row["id"] + "|o", row["original_code"], row["function_name"], calls))
        jobs.append(Job(row["id"] + "|t", row["target_code"], row["function_name"], calls))
    results = run_jobs(jobs, workers=4)
    for row in rows:
        for suffix in ("|o", "|t"):
            observed = results[row["id"] + suffix]
            assert observed.error is None, row["id"]
            for test, seen in zip(row["tests"], observed.results, strict=True):
                expect = test["expect"]
                assert seen["kind"] == expect["kind"], (row["id"], test)
                if expect["kind"] == "return":
                    assert seen["value"] == expect["value"], (row["id"], test)
                    restored = ast.literal_eval(expect["value"])
                    assert type(restored).__name__ == seen["type"], (row["id"], test)
                else:
                    assert seen["exception"] == expect["exception"], (row["id"], test)


def test_demonstration_cases_are_valid_and_reproducible():
    text = DEMO.read_text(encoding="utf-8")
    cases = [ReferenceCase.model_validate(item) for item in json.loads(text)]
    assert 5 <= len(cases) <= 6
    assert len({case.case_id for case in cases}) == len(cases)
    for case in cases:
        assert case.case_id.startswith("demo-") and case.source_group == "demo"
        assert gc.check_input(case.original_code).supported
        assert case.reference_code == gc.to_guard_clauses(case.original_code)
        assert gc.rubric(case.original_code, case.reference_code).passed
        assert case.tests and case.provenance and case.title
    assert demo_cases_json(build_demo_cases()) == text.replace("\r\n", "\n")


def test_demonstration_cases_are_independent_of_every_split(rows):
    cases = json.loads(DEMO.read_text(encoding="utf-8"))
    demo = [
        leakage.Fingerprint.of(case["case_id"], "demo", "demo", case[field])
        for case in cases
        for field in ("original_code", "reference_code")
    ]
    for field in ("original_code", "target_code"):
        prints = [
            leakage.Fingerprint.of(r["id"], r["split"], r["source_group"], r[field]) for r in rows
        ]
        report = leakage.compare(prints, demo, skip_same_split=False)
        assert report.flagged == []
    demo_code = {leakage.normalized_code(case["original_code"]) for case in cases}
    assert not demo_code & {leakage.normalized_code(r["original_code"]) for r in rows}


@pytest.mark.skipif(not PILOT.exists(), reason="no pilot fixtures in this checkout")
def test_heldout_records_do_not_duplicate_pilot_fixtures(rows):
    summary = validator.validate_extended(rows, near_duplicates=False, external=[PILOT], root=ROOT)
    assert summary["external_functions"] > 0

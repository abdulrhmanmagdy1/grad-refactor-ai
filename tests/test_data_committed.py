"""The committed dataset, its manifest, the frozen test split and the demonstration cases."""

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from refactor_ai.contracts import ReferenceCase
from refactor_ai.data import leakage, refgen
from refactor_ai.data.demo import build_demo_cases, demo_cases_json
from refactor_ai.data.executor import Job, run_jobs
from refactor_ai.tasks import guard_clauses as gc
from refactor_ai.verification.runner_child import same_value

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


# The case content of the frozen test split; it must never change (any prompt version).
FROZEN_TEST_CONTENT = "3a1e6b95ce74dbd1acdd76207eefcead31eeb255cc3b24a1e6d3955f90e75d12"


def test_frozen_test_case_content_never_changes():
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert validator.content_sha256(RECORDS, "test") == FROZEN_TEST_CONTENT
    assert frozen["content_sha256"] == FROZEN_TEST_CONTENT
    assert manifest["splits"]["test"]["content_sha256"] == FROZEN_TEST_CONTENT
    assert frozen["prompt_version"] == manifest["task"]["prompt_version"]
    # Every earlier freeze of the same cases stays in the history.
    previous = [entry for entry in frozen["history"] if entry.get("content_sha256")]
    assert previous and all(e["content_sha256"] == FROZEN_TEST_CONTENT for e in previous)
    assert all(e["split_sha256"] != frozen["split_sha256"] for e in previous)
    assert all(e.get("superseded_because") for e in previous)


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


# Known gaps of the committed reference tests, listed in docs/data-and-training/data-plan.md
# ("Reference tests"): record id, code to replace, replacement, and a witness call. The
# committed tests pass the changed function and the witness call tells it apart from the
# original. Without a witness the change only removes float noise: an exact comparison
# sees it, but the reference runner's float tolerance accepts every committed test.
REFERENCE_TEST_GAPS = [
    (
        "gc1-recipe-scaling-07",
        "return round(scaled, 1)",
        "return scaled",
        ("[100, 1]", "{'base_servings': 3}"),
    ),
    ("gc1-quiz-score-03", "if len(key) > 0:", "if len(key) >= 0:", ("[[], ()]", "{}")),
    ("gc1-savings-goal-01", "if months > 240:", "if months >= 240:", ("[12000, 0, 50]", "{}")),
    *[
        (f"gc1-card-checksum-0{n}", "digit = digit - 9", "pass", ("['0000000000000050']", "{}"))
        for n in range(1, 8)
    ],
    ("gc1-freight-quote-01", "return round(quote, 2)", "return quote", None),
    ("gc1-freight-quote-06", "return round(quote, 2)", "return quote", None),
]


def test_documented_reference_test_gaps_hold(rows):
    by_id = {row["id"]: row for row in rows}
    jobs = []
    for rid, old, new, witness in REFERENCE_TEST_GAPS:
        row = by_id[rid]
        assert row["original_code"].count(old) == 1, rid
        calls = tuple((t["args"], t["kwargs"]) for t in row["tests"]) + (
            (witness,) if witness else ()
        )
        changed = row["original_code"].replace(old, new)
        jobs.append(Job(rid + "|o", row["original_code"], row["function_name"], calls))
        jobs.append(Job(rid + "|c", changed, row["function_name"], calls))
    results = run_jobs(jobs, workers=2)
    for rid, _old, _new, witness in REFERENCE_TEST_GAPS:
        tests = by_id[rid]["tests"]
        assert results[rid + "|o"].error is None and results[rid + "|c"].error is None, rid
        original = [refgen.outcome_key(seen) for seen in results[rid + "|o"].results]
        changed = [refgen.outcome_key(seen) for seen in results[rid + "|c"].results]
        if witness:
            assert changed[: len(tests)] == original[: len(tests)], rid
            assert changed[-1] != original[-1], rid
            continue
        assert changed != original, rid
        for test, seen in zip(tests, results[rid + "|c"].results, strict=True):
            expect = test["expect"]
            assert seen["kind"] == expect["kind"], (rid, test)
            if expect["kind"] == "raise":
                assert seen["exception"] == expect["exception"], (rid, test)
            else:
                expected = ast.literal_eval(expect["value"])
                assert same_value(expected, ast.literal_eval(seen["value"])), (rid, test)


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

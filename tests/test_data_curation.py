"""Curation pipeline: families, formatting, explanations, mutants, test selection, splits,
leakage, determinism, manifest hashes, freeze protection and validator compatibility."""

import ast
import importlib.util
import json
import random
from pathlib import Path

import pytest

from refactor_ai.data import leakage, refgen
from refactor_ai.data.codegen import canonical_function
from refactor_ai.data.curate import RECORD_FIELDS, CurationConfig, curate, uses_findings
from refactor_ai.data.executor import JobResult
from refactor_ai.data.explain import explain, guard_changes
from refactor_ai.data.families import FAMILIES, all_families
from refactor_ai.data.families.base import Param
from refactor_ai.data.manifest import (
    FrozenSplitChanged,
    check_freeze,
    freeze_record,
    pretty_json,
    render_outputs,
)
from refactor_ai.data.mutation import mutants
from refactor_ai.data.splits import assign_family_splits
from refactor_ai.task_format import build_refactor_user_prompt, parse_refactor_output
from refactor_ai.tasks import guard_clauses as gc

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validator", ROOT / "scripts" / "validate_dataset.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

SMALL_FAMILIES = ["delivery-slot", "gift-card", "text-truncate"]


def test_every_family_builds_supported_variants():
    assert len(all_families()) >= 60
    for family in all_families():
        for attempt in range(3):
            variant = family.build(random.Random(f"test:{family.key}:{attempt}"))
            code = canonical_function(variant.render())
            check = gc.check_input(code)
            if not check.supported:
                assert check.reasons == ["no_opportunity"], (family.key, check.reasons)
                continue
            assert check.function_name == variant.name
            target = gc.to_guard_clauses(code)
            assert gc.rubric(code, target).passed, family.key


def test_canonical_formatting_keeps_else_if_nesting():
    code = (
        'def f(x):\n    if x:\n        return "a"\n    else:\n'
        "        if x is None:\n            return 1\n        else:\n            return 2\n"
    )
    canonical = canonical_function(code)
    assert "else:\n        if x is None:" in canonical
    assert "'a'" in canonical
    assert gc.code_nesting_depth(canonical) == gc.code_nesting_depth(code) == 2
    stock = ast.unparse(ast.parse(code))
    assert "elif x is None:" in stock  # the stock printer would hide the nesting
    assert gc.code_nesting_depth(stock + "\n") == 1


def test_calls_from_params_defaults_keywords_and_sampling():
    params = [
        Param("a", (1, 2)),
        Param("flag", (False, True), default=False),
        Param("mode", ("x",), default="x", kw_only=True),
    ]
    calls = refgen.calls_from_params(params, "k")
    assert calls == [
        ("[1]", "{}"),
        ("[1]", "{'flag': True}"),
        ("[2]", "{}"),
        ("[2]", "{'flag': True}"),
    ]
    big = [Param("a", tuple(range(30))), Param("b", tuple(range(30)))]
    sample = refgen.calls_from_params(big, "seed-a", max_calls=50)
    assert len(sample) == 50 and sample == refgen.calls_from_params(big, "seed-a", max_calls=50)
    assert sample != refgen.calls_from_params(big, "seed-b", max_calls=50)


EXPLAINED = """def ship(weight, zone):
    if weight > 0:
        if zone in ('a', 'b'):
            if zone == 'a':
                return 1
            elif zone == 'b':
                return 2
            else:
                return 3
        else:
            return None
    else:
        raise ValueError('bad weight')
"""


def test_explanation_matches_the_reference_transformation():
    target = gc.to_guard_clauses(EXPLAINED)
    text = explain(EXPLAINED, target)
    changes = guard_changes(EXPLAINED)
    target_tests = {
        ast.unparse(node.test) for node in ast.walk(ast.parse(target)) if isinstance(node, ast.If)
    }
    assert [c.condition for c in changes][:2] == ["weight <= 0", "zone not in ('a', 'b')"]
    for change in changes:
        assert change.condition in target_tests
    assert "`weight <= 0` raises ValueError" in text
    assert "`zone not in ('a', 'b')` returns None" in text
    depth = (gc.code_nesting_depth(EXPLAINED), gc.code_nesting_depth(target))
    assert f"from {depth[0]} to {depth[1]}." in text
    assert "1 more check exits early" in text and "1 more checks" not in text
    assert len(text) <= 600


def test_explanation_never_lists_an_untransformed_elif():
    code = (
        "def f(x, y):\n    if x is None:\n        return 0\n    elif y:\n        if x > 1:\n"
        "            return 1\n        else:\n            return 2\n    else:\n        return 3\n"
    )
    target = gc.to_guard_clauses(code)
    target_tests = {
        ast.unparse(node.test) for node in ast.walk(ast.parse(target)) if isinstance(node, ast.If)
    }
    for change in guard_changes(code):
        assert change.condition in target_tests


def test_mutants_are_distinct_valid_and_deterministic():
    first = mutants(EXPLAINED)
    assert first == mutants(EXPLAINED)
    dumps = {ast.dump(ast.parse(m.code)) for m in first}
    assert len(dumps) == len(first)
    assert ast.dump(ast.parse(EXPLAINED)) not in dumps
    assert {m.operator for m in first} >= {"compare", "negate_if", "drop_exit"}


def outcome(kind, value=None, lines=(), line=None, exception="ValueError", type_name="int"):
    if kind == "return":
        return {"kind": "return", "value": value, "type": type_name, "lines": list(lines)}
    if kind == "raise":
        return {"kind": "raise", "exception": exception, "line": line, "lines": list(lines)}
    return {"kind": kind, "lines": list(lines)}


PLAN_CODE = (
    "def f(x):\n    if x < 0:\n        raise ValueError('neg')\n"
    "    if x == 0:\n        return 0\n    return x\n"
)


def plan(results0, results1=None, target=None, mutant_results=None, **kwargs):
    calls = [(repr([i]), "{}") for i in range(len(results0))]
    branches = JobResult("b", [{"kind": "return", "branches": []} for _ in results0])
    return refgen.build_test_plan(
        PLAN_CODE,
        calls,
        JobResult("o", results0),
        JobResult("o1", results1 or results0),
        branches,
        JobResult("t", target or results0),
        mutant_results or {},
        2,
        **kwargs,
    )


def test_test_plan_requires_every_return_and_raise():
    covered = [
        outcome("raise", lines=(2, 3), line=3),
        outcome("return", "0", lines=(2, 4, 5)),
        outcome("return", "5", lines=(2, 4, 6)),
    ]
    result = plan(covered)
    assert isinstance(result, refgen.TestPlan)
    assert result.metrics["exit_lines_covered"] == result.metrics["exit_lines"] == 3
    rejected = plan(covered[1:])
    assert isinstance(rejected, refgen.Rejection) and rejected.reason == "uncovered_exit_lines"


def test_test_plan_rejects_differential_mismatch_and_discards_unstable_calls():
    good = [
        outcome("raise", lines=(2, 3), line=3),
        outcome("return", "0", lines=(2, 4, 5)),
        outcome("return", "5", lines=(2, 4, 6)),
    ]
    changed_target = [good[0], good[1], outcome("return", "6", lines=(2, 4, 6))]
    mismatch = plan(good, target=changed_target)
    assert isinstance(mismatch, refgen.Rejection) and mismatch.reason == "differential_mismatch"
    noisy = good + [
        outcome("return", "7", lines=(2, 4, 6)),
        outcome("raise", lines=(2,), line=2, exception="TypeError"),
        outcome("timeout"),
    ]
    seed1 = good + [outcome("return", "8", lines=(2, 4, 6)), noisy[4], noisy[5]]
    result = plan(noisy, results1=seed1)
    assert isinstance(result, refgen.TestPlan)
    assert result.discarded == {
        "hash_seed_dependent": 1,
        "incidental_exception": 1,
        "original_timeout": 1,
    }
    assert all(test["args"] in ("[0]", "[1]", "[2]") for test in result.tests)


def test_test_plan_prefers_mutant_kills_and_new_outcomes():
    results = [
        outcome("raise", lines=(2, 3), line=3),
        outcome("return", "0", lines=(2, 4, 5)),
        outcome("return", "5", lines=(2, 4, 6)),
        outcome("return", "9", lines=(2, 4, 6)),
    ]
    killer = JobResult("m0", [results[0], results[1], results[2], outcome("return", "8")])
    chosen = plan(results, mutant_results={"m0": killer}, min_tests=1, diverse_tests=1)
    assert "[3]" in [test["args"] for test in chosen.tests]
    assert chosen.metrics["mutants_killed"] == chosen.metrics["mutants_killable"] == 1


def test_split_assignment_is_deterministic_diverse_and_respects_train_only():
    families = [(f"f{i}", f"c{i % 5}") for i in range(20)]
    first = assign_family_splits(
        families, seed=1, validation=3, test=3, train_only=frozenset({"f0"})
    )
    assert first == assign_family_splits(
        families, seed=1, validation=3, test=3, train_only=frozenset({"f0"})
    )
    assert first["f0"] == "train"
    held = {split: [k for k, v in first.items() if v == split] for split in ("validation", "test")}
    assert len(held["validation"]) == len(held["test"]) == 3
    categories = dict(families)
    assert len({categories[k] for k in held["test"]}) == 3
    with pytest.raises(ValueError):
        assign_family_splits(families[:4], seed=1, validation=2, test=2)


def test_near_duplicate_rule_and_external_extraction(tmp_path):
    base = EXPLAINED
    renamed = EXPLAINED.replace("return 3", "return 4")  # one literal differs
    unrelated = (
        "def other(a):\n    if a:\n        return 'x'\n    else:\n        raise KeyError('k')\n"
    )
    near = leakage.compare(
        [leakage.Fingerprint.of("a", "train", "g1", base)],
        [
            leakage.Fingerprint.of("b", "test", "g2", renamed),
            leakage.Fingerprint.of("c", "test", "g3", unrelated),
        ],
    )
    assert near.pairs_examined == 2
    assert [(p.left, p.right) for p in near.flagged] == [("a", "b")]
    module = tmp_path / "fixtures.py"
    module.write_text(
        f"CASES = [{{'code': '''\n{base}'''}}]\n\ndef helper():\n    return 1\n", encoding="utf-8"
    )
    records = tmp_path / "records.jsonl"
    records.write_text(
        json.dumps({"original_code": unrelated, "prompt": build_refactor_user_prompt(base)}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text(
        "def ignored():\n    return 1\n", encoding="utf-8"
    )
    codes, inventory = leakage.external_code([tmp_path], tmp_path)
    labels = [label for label, _ in codes]
    assert any(label.endswith(":string") for label in labels)
    assert any(label.endswith(":def") for label in labels)
    assert any(label.endswith(".original_code") for label in labels)
    assert any(label.endswith(".prompt") for label in labels)
    assert all("__pycache__" not in item["path"] for item in inventory)


@pytest.fixture(scope="module")
def small_run(tmp_path_factory):
    external = tmp_path_factory.mktemp("external")
    config = CurationConfig(
        root=ROOT,
        families=SMALL_FAMILIES,
        validation_families=1,
        test_families=1,
        train_variants=4,
        heldout_variants=3,
        real_sources=(),
        external_paths=(external,),
        demo_path=external / "no-demo.json",
        workers=4,
    )
    return config, curate(config)


def test_small_curation_is_deterministic(small_run):
    config, first = small_run
    second = curate(config)
    assert first.records == second.records
    assert first.metadata == second.metadata
    assert first.log == second.log
    assert render_outputs(first, ROOT) == render_outputs(second, ROOT)


def test_small_curation_records_follow_the_contract(small_run):
    _config, result = small_run
    records = result.records
    assert {r["split"] for r in records} == {"train", "validation", "test"}
    groups = {}
    for record in records:
        assert tuple(record) == RECORD_FIELDS
        assert groups.setdefault(record["source_group"], record["split"]) == record["split"]
        check = gc.check_input(record["original_code"])
        assert check.supported and check.function_name == record["function_name"]
        assert record["target_code"] == gc.to_guard_clauses(record["original_code"])
        assert gc.rubric(record["original_code"], record["target_code"]).passed
        parsed = parse_refactor_output(record["completion"])
        assert parsed.error is None and not parsed.repaired
        assert parsed.code == record["target_code"]
        has_notes = "Analysis notes:" in record["prompt"]
        assert has_notes == (record["split"] == "train" and uses_findings(record["id"], 20261020))
        assert record["tests"] and record["license"] and record["provenance"]
    path = Path(_write(records))
    assert len(validator.load_and_validate(path)) == len(records)
    summary = validator.validate_extended(records)
    assert summary["records_checked"] == len(records)


def _write(records):
    import tempfile

    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    with handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return handle.name


def test_reference_tests_match_original_and_target(small_run):
    from refactor_ai.data.executor import Job, run_jobs

    _config, result = small_run
    jobs = []
    for record in result.records:
        calls = tuple((t["args"], t["kwargs"]) for t in record["tests"])
        jobs.append(
            Job(record["id"] + "|o", record["original_code"], record["function_name"], calls)
        )
        jobs.append(Job(record["id"] + "|t", record["target_code"], record["function_name"], calls))
    outputs = run_jobs(jobs, workers=4)
    for record in result.records:
        for suffix in ("|o", "|t"):
            observed = outputs[record["id"] + suffix].results
            for test, seen in zip(record["tests"], observed, strict=True):
                expect = test["expect"]
                assert seen["kind"] == expect["kind"]
                if expect["kind"] == "return":
                    assert seen["value"] == expect["value"]
                else:
                    assert seen["exception"] == expect["exception"]


def test_external_fixture_duplicate_removes_the_heldout_record(tmp_path):
    config = CurationConfig(
        root=ROOT,
        families=SMALL_FAMILIES,
        validation_families=1,
        test_families=1,
        train_variants=2,
        heldout_variants=2,
        real_sources=(),
        external_paths=(tmp_path,),
        demo_path=tmp_path / "none.json",
    )
    baseline = curate(config)
    victim = next(r for r in baseline.records if r["split"] == "test")
    (tmp_path / "pilot.jsonl").write_text(
        json.dumps({"original_code": victim["original_code"]}) + "\n", encoding="utf-8"
    )
    rerun = curate(config)
    assert victim["id"] not in {r["id"] for r in rerun.records}
    reasons = {(e["candidate"], e["reason"]) for e in rerun.log["exclusions"]}
    assert (victim["id"], "near_duplicate_external_pilot") in reasons


def test_demo_overlap_is_an_error(tmp_path):
    config = CurationConfig(
        root=ROOT,
        families=SMALL_FAMILIES,
        validation_families=1,
        test_families=1,
        train_variants=2,
        heldout_variants=2,
        real_sources=(),
        external_paths=(tmp_path,),
        demo_path=tmp_path / "demo.json",
    )
    record = curate(config).records[0]
    demo = [{"case_id": "demo-copy", "original_code": record["original_code"]}]
    (tmp_path / "demo.json").write_text(json.dumps(demo), encoding="utf-8")
    with pytest.raises(ValueError, match="demonstration cases overlap"):
        curate(config)


def test_manifest_hashes_and_freeze_protection(small_run, tmp_path):
    _config, result = small_run
    outputs = render_outputs(result, ROOT)
    records_text = outputs["datasets/guard_clauses/v1/records.jsonl"]
    manifest = json.loads(outputs["datasets/guard_clauses/v1/manifest.json"])
    path = tmp_path / "records.jsonl"
    path.write_text(records_text.replace("\n", "\r\n"), encoding="utf-8", newline="")
    assert validator.file_sha256(path) == manifest["files"]["records"]["sha256"]
    for split in ("train", "validation", "test"):
        assert validator.split_sha256(path, split) == manifest["splits"][split]["sha256"]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert validator.verify_manifest(path, manifest_path) == []

    root = tmp_path / "repo"
    (root / "experiments" / "data").mkdir(parents=True)
    assert check_freeze(outputs, root) is None
    frozen = freeze_record(manifest, git_head=None)
    (root / "experiments" / "data" / "test-split-freeze.json").write_text(
        pretty_json(frozen), encoding="utf-8"
    )
    assert check_freeze(outputs, root)["split_sha256"] == manifest["splits"]["test"]["sha256"]
    freeze_path = root / "experiments" / "data" / "test-split-freeze.json"
    assert validator.verify_freeze(path, freeze_path) == []
    frozen["split_sha256"] = "0" * 64
    freeze_path.write_text(pretty_json(frozen), encoding="utf-8")
    with pytest.raises(FrozenSplitChanged):
        check_freeze(outputs, root)
    assert validator.verify_freeze(path, freeze_path) == [
        "test split hash differs from the frozen hash"
    ]


def test_family_registry_keys_are_stable_group_names():
    assert all(key == key.lower() and " " not in key for key in FAMILIES)

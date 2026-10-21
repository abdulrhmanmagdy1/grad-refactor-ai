"""The committed protocol freeze record (eval-v1) and the validation evidence it rests on.

These tests read committed files only; nothing here runs a model or reads the test split's
outcomes. If a frozen file changes, test_the_guard_accepts_the_committed_freeze_record
fails on purpose: after the freeze, a change to the frozen code needs a new protocol
version, or, before any test-split run, a documented re-freeze.
"""

import hashlib
import itertools
import json
from pathlib import Path

import pytest

from refactor_ai.evaluation import cases, protocol, report, targets

ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = ROOT / protocol.PROTOCOL_FREEZE_PATH
EVIDENCE = ROOT / "experiments" / "evaluation" / "validation-2026-10-21"
EVALUATION_ID = "kaggle-grad-refactor-ai-eval-600603dc"
RECORDS = EVIDENCE / "evaluation" / EVALUATION_ID / "records.jsonl"
DATASET = ROOT / cases.DEFAULT_DATASET


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def freeze() -> dict:
    return load(FREEZE_PATH)


@pytest.fixture(scope="module")
def validation_rows() -> list[dict]:
    return report.load_records([RECORDS])


def test_the_guard_accepts_the_committed_freeze_record(freeze):
    problems = protocol.check_protocol_freeze(
        freeze,
        records_path=DATASET,
        test_freeze=load(ROOT / protocol.TEST_FREEZE_PATH),
        code=protocol.frozen_code_sha256(),
    )
    assert problems == [], "\n".join(problems)
    assert protocol.protocol_state(ROOT)["status"] == "frozen"
    assert freeze["frozen_code"]["patterns"] == list(protocol.FROZEN_CODE_PATTERNS)


def test_the_frozen_settings_are_the_validation_run_settings(freeze):
    run = load(EVIDENCE / "evaluation" / EVALUATION_ID / "run.json")
    assert freeze["arms"] == run["arms"] == protocol.frozen_arm_settings()
    for arm, settings in freeze["arms"].items():
        generation = settings["generation"]
        assert generation["refactor"]["max_new_tokens"] == 768, arm
        assert generation["analysis"]["max_new_tokens"] == 384, arm
        assert generation["review"]["max_new_tokens"] == 384, arm
        assert {config["max_input_tokens"] for config in generation.values()} == {2048}
    assert run["dataset_sha256"] == freeze["data"]["dataset_sha256"]


def test_the_frozen_model_is_the_trained_and_validated_adapter(freeze):
    model = freeze["model"]
    training = load(ROOT / "experiments" / "training" / "full-2026-10-21.json")
    assert model["adapter_id"] == training["run_id"]
    assert model["adapter_sha256"] == training["artifact_sha256"]
    assert model["adapter_config_sha256"] == training["adapter_config_sha256"]
    assert (model["model_id"], model["model_revision"]) == (
        training["model_id"],
        training["model_revision"],
    )
    run = load(EVIDENCE / "evaluation" / EVALUATION_ID / "run.json")
    for key in protocol.FROZEN_MODEL_KEYS:
        assert run["provider"][key] == model[key]
    for call in run["warm_up"]["provider_calls"]:
        assert {key: call["model"][key] for key in protocol.FROZEN_MODEL_KEYS} == {
            key: model[key] for key in protocol.FROZEN_MODEL_KEYS
        }


def test_the_evidence_is_the_kaggle_output(freeze):
    manifest = load(EVIDENCE / "outputs-manifest.json")
    for relative, digest in manifest.items():
        assert protocol.lf_sha256(EVIDENCE / relative) == digest, relative
    assert freeze["validation_baseline"]["records_sha256"] == protocol.lf_sha256(RECORDS)
    status = load(EVIDENCE / "status.json")
    assert status["ok"] and status["job"]["split"] == "validation"
    assert freeze["validation_baseline"]["bundle_sha256"] == status["bundle"]["bundle_sha256"]


def test_the_recorded_baseline_is_what_the_records_say(freeze, validation_rows):
    assert {row["split"] for row in validation_rows} == {"validation"}
    metrics = report.arm_metrics(validation_rows)
    recorded = freeze["validation_baseline"]["recorded"]
    for arm, by_metric in recorded.items():
        for metric, count in by_metric.items():
            assert metrics[arm]["rates"][metric]["numerator"] == count, (arm, metric)
    assert {arm: recorded[arm]["proposal_ready"] for arm in "ABCD"} == {
        "A": 6,
        "B": 3,
        "C": 69,
        "D": 46,
    }


def attainable(validation_rows: list[dict], undetermined: dict[str, list[str]]) -> dict:
    """Least and most validation counts once undetermined records may go either way."""
    predicates = {
        "proposal_ready": lambda r: bool(r["proposal_ready"]),
        "syntax_valid": lambda r: r["run_status"] == "completed" and r["syntax"] == "pass",
        "failed": lambda r: r["run_status"] == "failed",
    }
    counts: dict = {}
    for arm in "ABCD":
        rows = [r for r in validation_rows if r["arm"] == arm]
        open_rows = [r for r in rows if r["case_id"] in undetermined.get(arm, [])]
        counts[arm] = {}
        for metric, predicate in predicates.items():
            recorded = sum(predicate(r) for r in rows)
            counts[arm][metric] = [
                recorded - sum(predicate(r) for r in open_rows),
                recorded + sum(not predicate(r) for r in open_rows),
            ]
    return counts


def test_the_targets_follow_the_stated_rule(freeze, validation_rows):
    check = load(EVIDENCE / "code-change-check.json")
    undetermined = check["replay"]["undetermined_records_by_arm"]
    counts = attainable(validation_rows, undetermined)
    assert freeze["validation_baseline"]["attainable_under_frozen_code"] == counts
    frozen = freeze["targets"]
    assert frozen["rule"] == targets.RULE
    assert frozen["arms"] == targets.derive_arm_targets(counts, n=84, test_n=88)
    # Expected directions: the same significant sign in every attainable outcome.
    open_records = [(arm, case) for arm, ids in undetermined.items() for case in ids]
    by_comparison: dict[str, set] = {}
    for outcome in itertools.product([False, True], repeat=len(open_records)):
        changed = dict(zip(open_records, outcome, strict=True))
        rows = [
            dict(r, proposal_ready=changed.get((r["arm"], r["case_id"]), r["proposal_ready"]))
            for r in validation_rows
        ]
        for item in report.paired_comparisons(rows):
            first, second = item["comparison"].split(" vs ")
            seen = targets.direction(
                item[f"{first}_only"], item[f"{second}_only"], item["holm_adjusted_p"]
            )
            by_comparison.setdefault(item["comparison"], set()).add(seen)
    expected = {
        name: seen.pop() if len(seen) == 1 else "none" for name, seen in by_comparison.items()
    }
    assert {d["comparison"]: d["expected"] for d in frozen["directions"]} == expected
    assert expected == {"B vs A": "none", "C vs A": "first", "D vs C": "second", "D vs B": "first"}


def test_the_validation_baseline_meets_its_own_targets(freeze, validation_rows, tmp_path):
    written = report.build_report(validation_rows, tmp_path, freeze=freeze)
    assessment = load(Path(written["report.json"]))["targets"]
    assert all(row["met"] is True for row in assessment["arms"])
    outcomes = {item["comparison"]: item["outcome"] for item in assessment["comparisons"]}
    assert outcomes == {
        "B vs A": "no direction expected",
        "C vs A": "confirmed",
        "D vs C": "confirmed",
        "D vs B": "confirmed",
    }


def test_the_test_split_hashes_are_the_frozen_split(freeze):
    test_freeze = load(ROOT / protocol.TEST_FREEZE_PATH)
    split = freeze["data"]["test_split"]
    assert split["split_sha256"] == test_freeze["split_sha256"]
    assert split["content_sha256"] == test_freeze["content_sha256"]
    assert split["count"] == test_freeze["count"] == 88
    assert freeze["data"]["prompt_version"] == test_freeze["prompt_version"] == "refactor-v2"
    text = DATASET.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert hashlib.sha256(text.encode()).hexdigest() == freeze["data"]["dataset_sha256"]

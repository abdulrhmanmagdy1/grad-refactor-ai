"""The contract examples in docs/architecture/examples/ are valid, complete and current."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from refactor_ai.agents.coordinator import COMPLETED_STOP_REASONS, FAILED_STOP_REASONS
from refactor_ai.contracts import Disposition, HealthResponse, RunList, RunRecord, RunStatus
from refactor_ai.runs.components import ADAPTER_MISSING_REASON, MODEL_LOADING_DETAIL
from refactor_ai.runs.errors import ErrorCode
from refactor_ai.runs.records import summarize

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "docs" / "architecture" / "examples"
SCRIPT = ROOT / "scripts" / "export_contract_examples.py"
REGENERATE = "run: python -m uv run python scripts/export_contract_examples.py"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_contract_examples", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


exporter = _load_exporter()
EXPECTED = exporter.build_examples()
RECORD_FILES = sorted(name for name in EXPECTED if name.startswith("run_record_"))
ERROR_FILES = sorted(name for name in EXPECTED if name.startswith("error_"))


def read(name: str) -> str:
    # Git may check the files out with CRLF on Windows; the content is compared as LF.
    return (EXAMPLES_DIR / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def record(name: str) -> RunRecord:
    return RunRecord.model_validate_json(read(name))


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_exists_and_is_current(name):
    assert (EXAMPLES_DIR / name).is_file(), f"missing example {name}; {REGENERATE}"
    assert read(name) == EXPECTED[name].render(), f"stale example {name}; {REGENERATE}"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_validates_against_its_model(name):
    adapter = TypeAdapter(EXPECTED[name].schema)
    text = read(name)
    value = adapter.validate_json(text)
    # Round trip: every field in the file belongs to the model and none is dropped.
    assert json.loads(text) == adapter.dump_python(value, mode="json")


def test_no_missing_or_unexpected_example_files():
    present = {path.name for path in EXAMPLES_DIR.glob("*.json")}
    assert present - set(EXPECTED) == set(), f"unexpected example files; {REGENERATE}"
    assert set(EXPECTED) - present == set(), f"missing example files; {REGENERATE}"


def test_check_mode_agrees():
    assert exporter.stale_examples() == []
    assert exporter.main(["--check"]) == 0


def test_required_examples_exist():
    required = {
        "run_create_request.json",
        "run_accepted.json",
        "run_record_queued.json",
        "run_record_proposal_ready.json",
        "run_record_no_change.json",
        "run_record_rejected.json",
        "run_record_failed.json",
        "run_record_interrupted.json",
        "run_list.json",
        "health_fake.json",
        "health_local.json",
        "health_local_loading.json",
        "health_local_adapter_missing.json",
        "run_record_adapter_unavailable.json",
        "reference_cases.json",
        "analysis_report.json",
        "review_result.json",
        "decision_request.json",
        "error_validation_error.json",
        "error_invalid_syntax.json",
        "error_unknown_reference_case.json",
        "error_reference_case_mismatch.json",
        "error_busy.json",
        "error_run_not_found.json",
        "error_proposal_unavailable.json",
    }
    assert required <= set(EXPECTED)


@pytest.mark.parametrize("name", ERROR_FILES)
def test_error_examples_use_documented_codes(name):
    body = json.loads(read(name))
    assert set(body) == {"error"}
    code = body["error"]["code"]
    assert code in {item.value for item in ErrorCode}
    assert name == f"error_{code}.json"
    assert body["error"]["message"]


def test_run_record_examples_cover_the_states():
    states = {name: summarize(record(name)) for name in RECORD_FILES}
    expected = {
        "run_record_queued.json": (RunStatus.QUEUED, None),
        "run_record_analyzing.json": (RunStatus.ANALYZING, None),
        "run_record_proposal_ready.json": (RunStatus.COMPLETED, Disposition.PROPOSAL_READY),
        "run_record_uncertain.json": (RunStatus.COMPLETED, Disposition.UNCERTAIN),
        "run_record_no_change.json": (RunStatus.COMPLETED, Disposition.NO_CHANGE),
        "run_record_rejected.json": (RunStatus.COMPLETED, Disposition.REJECTED),
        "run_record_failed.json": (RunStatus.FAILED, Disposition.FAILED),
        "run_record_adapter_unavailable.json": (RunStatus.FAILED, Disposition.FAILED),
        "run_record_interrupted.json": (RunStatus.FAILED, Disposition.FAILED),
    }
    assert {name: (s.status, s.disposition) for name, s in states.items()} == expected
    assert record("run_record_interrupted.json").error.code == "interrupted"
    assert record("run_record_failed.json").error.code == "timeout"
    adapter = record("run_record_adapter_unavailable.json")
    assert adapter.error.code == "adapter_unavailable"
    assert adapter.settings.refactor_use_adapter is True and adapter.call_count == 0


def test_run_record_examples_are_labelled_fake():
    for name in RECORD_FILES:
        item = record(name)
        assert item.provider_mode == "fake"
        assert item.explanation is None or item.explanation.startswith(
            "FAKE PROVIDER (not a model):"
        )


def test_run_list_is_newest_first_and_summarizes_the_records():
    runs = RunList.model_validate_json(read("run_list.json")).runs
    created = [run.created_at for run in runs]
    assert created == sorted(created, reverse=True)
    by_id = {record(name).run_id: record(name) for name in RECORD_FILES}
    assert [run.run_id for run in runs] == [
        r.run_id for r in sorted(by_id.values(), key=lambda r: r.created_at, reverse=True)
    ]
    for run in runs:
        assert summarize(by_id[run.run_id]) == run


COORDINATED = (
    "run_record_proposal_ready.json",
    "run_record_uncertain.json",
    "run_record_no_change.json",
    "run_record_rejected.json",
    "run_record_failed.json",
)


@pytest.mark.parametrize("name", COORDINATED)
def test_coordinator_records_use_documented_stop_reasons_and_reason_codes(name):
    item = record(name)
    allowed = COMPLETED_STOP_REASONS if item.status == RunStatus.COMPLETED else FAILED_STOP_REASONS
    assert item.stop_reason in allowed
    for reason in item.verification.disposition_reasons:
        code, _, sentence = reason.partition(": ")
        assert code and code.replace("_", "").isalnum() and sentence, reason
    assert item.warnings, "the coordinator labels fake-provider output in warnings"
    assert all(t.elapsed_s >= 0 for t in item.stage_timings)
    assert item.finished_at >= item.started_at >= item.created_at


def test_health_examples_cover_adapter_and_loading_states():
    adapter_missing = HealthResponse.model_validate_json(read("health_local_adapter_missing.json"))
    assert adapter_missing.refactor_use_adapter is True
    assert adapter_missing.provider.ready is False
    assert adapter_missing.provider.detail.startswith(ADAPTER_MISSING_REASON)
    loading = HealthResponse.model_validate_json(read("health_local_loading.json"))
    assert loading.provider.detail == MODEL_LOADING_DETAIL
    fake = HealthResponse.model_validate_json(read("health_fake.json"))
    assert fake.refactor_use_adapter is False and fake.mode == "fake"


def test_replayed_runner_results_are_used_for_reference_tests():
    proposal = record("run_record_proposal_ready.json").verification.reference_tests
    rejected = record("run_record_rejected.json").verification.reference_tests
    assert (proposal.status, proposal.passed, proposal.total) == ("pass", 4, 4)
    assert rejected.status == "fail" and rejected.failures[0].kind == "missing_exception"
    expected = [replay.result for replay in exporter.captured_results()]
    assert proposal == expected[0] and rejected == expected[1]

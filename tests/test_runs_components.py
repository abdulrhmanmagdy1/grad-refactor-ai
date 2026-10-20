"""Lazy wiring of the workflow, local provider, reference runner and demonstration cases."""

import json
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from refactor_ai.config import Settings
from refactor_ai.contracts import (
    ChatMessage,
    GenerationRequest,
    ProviderErrorCode,
    ProviderInfo,
    ProviderMode,
    ReferenceCase,
    Role,
    RunnerInfo,
    RunStatus,
    WorkflowRequest,
    WorkflowSettings,
)
from refactor_ai.providers.fake import FakeProvider
from refactor_ai.runs import components
from refactor_ai.runs.components import (
    ADAPTER_MISSING_REASON,
    MODEL_LOADING_DETAIL,
    RUNNER_CHECKS_RUNNING,
    RUNNER_DISABLED_REASON,
    CasesUnavailableError,
    DisabledRunner,
    ProviderWarmup,
    RunnerMonitor,
    StaticCaseRegistry,
    UnavailableCaseRegistry,
    UnavailableProvider,
    adapter_problem,
    as_registry,
    build_provider,
    build_registry,
    build_runner,
    build_workflow,
    describe_exception,
    provider_health_info,
    redact_host_paths,
    runner_info,
)

CODE = "def f(x):\n    return x\n"


def case(case_id="demo", task_type="guard_clauses", **extra) -> dict:
    return {
        "case_id": case_id,
        "task_type": task_type,
        "function_name": "f",
        "original_code": CODE,
        **extra,
    }


def fake_module(monkeypatch, name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


# --- provider ------------------------------------------------------------------------


def test_fake_provider_by_default():
    provider = build_provider(Settings())
    assert isinstance(provider, FakeProvider)
    assert provider.mode == ProviderMode.FAKE


def test_missing_local_provider_is_reported_not_replaced(monkeypatch):
    monkeypatch.setitem(sys.modules, components.LOCAL_PROVIDER_MODULE, None)
    provider = build_provider(Settings(provider="local"))
    assert isinstance(provider, UnavailableProvider)
    assert provider.mode == ProviderMode.LOCAL_MODEL
    info = provider.info()
    assert (info.provider_mode, info.ready) == (ProviderMode.LOCAL_MODEL, False)
    assert "not available" in info.detail
    request = GenerationRequest(
        role=Role.REFACTOR, messages=[ChatMessage(role="user", content="x")]
    )
    result = provider.generate(request)
    assert result.error.code == ProviderErrorCode.UNAVAILABLE
    assert result.provider_mode == ProviderMode.LOCAL_MODEL
    provider.close()


def test_local_provider_is_created_from_the_configured_file(monkeypatch, tmp_path):
    created = []

    class LocalProvider:
        mode = ProviderMode.LOCAL_MODEL

        @classmethod
        def from_config(cls, path):
            created.append(path)
            return cls()

    fake_module(monkeypatch, components.LOCAL_PROVIDER_MODULE, LocalProvider=LocalProvider)
    config = tmp_path / "model.local.json"
    provider = build_provider(Settings(provider="local", local_model_config=config))
    assert isinstance(provider, LocalProvider)
    assert created == [config]


def test_local_provider_start_failure_hides_host_paths(monkeypatch):
    home = str(Path.home())

    class LocalProvider:
        @classmethod
        def from_config(cls, path):
            raise FileNotFoundError(f"No such file: {home}\\project\\configs\\model.local.json")

    fake_module(monkeypatch, components.LOCAL_PROVIDER_MODULE, LocalProvider=LocalProvider)
    provider = build_provider(Settings(provider="local"))
    assert isinstance(provider, UnavailableProvider)
    detail = provider.info().detail
    assert "could not start" in detail and "FileNotFoundError" in detail
    assert home not in detail and "~" in detail


def test_real_local_provider_parses_config_without_starting_a_worker(tmp_path):
    local = pytest.importorskip("refactor_ai.providers.local")
    config = tmp_path / "model.local.json"
    config.write_text(
        json.dumps(
            {
                "python": "missing-python.exe",
                "model_dir": "missing-model",
                "model_id": "example/model",
                "model_revision": "0" * 40,
            }
        ),
        encoding="utf-8",
    )
    provider = build_provider(Settings(provider="local", local_model_config=config))
    try:
        assert isinstance(provider, local.LocalProvider)
        info = provider.info()
        assert info.provider_mode == ProviderMode.LOCAL_MODEL
        assert info.ready is False
        assert provider.worker_pid is None
    finally:
        provider.close()


# --- runner --------------------------------------------------------------------------


def test_disabled_runner_setting():
    runner = build_runner(Settings(runner="disabled"))
    assert isinstance(runner, DisabledRunner)
    assert runner.info().enabled is False
    assert runner.info().reason == RUNNER_DISABLED_REASON
    reference = ReferenceCase.model_validate(case())
    result = runner.run(reference, CODE)
    assert (result.status, result.case_id, result.reason) == (
        "not_run",
        "demo",
        RUNNER_DISABLED_REASON,
    )


def test_missing_runner_is_reported_disabled(monkeypatch):
    monkeypatch.setitem(sys.modules, components.VERIFICATION_MODULE, None)
    runner = build_runner(Settings(runner="auto"))
    assert isinstance(runner, DisabledRunner)
    assert runner.info().enabled is False
    assert "not available" in runner.info().reason


def test_runner_factory_is_used_when_present(monkeypatch):
    sentinel = object()
    fake_module(monkeypatch, components.VERIFICATION_MODULE, create_runner=lambda: sentinel)
    assert build_runner(Settings(runner="auto")) is sentinel


def test_failing_runner_factory_is_reported(monkeypatch):
    def create_runner():
        raise RuntimeError("isolation check crashed")

    fake_module(monkeypatch, components.VERIFICATION_MODULE, create_runner=create_runner)
    runner = build_runner(Settings())
    assert isinstance(runner, DisabledRunner)
    assert "RuntimeError" in runner.info().reason


def test_runner_module_without_a_factory_is_reported(monkeypatch):
    fake_module(monkeypatch, components.VERIFICATION_MODULE)
    runner = build_runner(Settings())
    assert isinstance(runner, DisabledRunner)
    assert "create_runner" in runner.info().reason


class SlowRunner:
    def __init__(self, error=None):
        self.release = threading.Event()
        self.error = error
        self.calls = 0

    def info(self):
        self.calls += 1
        assert self.release.wait(5)
        if self.error is not None:
            raise self.error
        return RunnerInfo(enabled=True, isolation={"separate_process": True})

    def run(self, case, candidate_code):
        raise AssertionError("not used")


def test_runner_monitor_reports_checks_in_progress_without_waiting():
    runner = SlowRunner()
    monitor = RunnerMonitor(runner)
    monitor.start()
    try:
        assert monitor.wait(0.05) is False
        started = time.monotonic()
        info = monitor.info()
        assert time.monotonic() - started < 0.5
        assert (info.enabled, info.reason) == (False, RUNNER_CHECKS_RUNNING)
        assert monitor.checked is False
    finally:
        runner.release.set()
    assert monitor.wait(5) is True and monitor.join(5) is True
    assert monitor.info() == RunnerInfo(enabled=True, isolation={"separate_process": True})


def test_runner_monitor_survives_a_failing_check():
    runner = SlowRunner(error=RuntimeError("probe crashed"))
    runner.release.set()
    monitor = RunnerMonitor(runner)
    monitor.start()
    assert monitor.wait(5) and monitor.join(5)
    info = monitor.info()
    assert info.enabled is False
    assert info.reason == "Reference runner information is unavailable (RuntimeError)."


def test_runner_monitor_without_a_runner():
    monitor = RunnerMonitor(None)
    monitor.start()
    assert monitor.checked
    assert monitor.info() == RunnerInfo(enabled=False, reason="No reference runner is configured.")
    assert monitor.join(0) is True


def test_runner_info_accepts_mappings_and_hides_home_paths():
    home = str(Path.home())

    class MappingRunner:
        def info(self):
            return {"enabled": False, "reason": f"interpreter missing under {home}\venv"}

    info = runner_info(MappingRunner())
    assert info.enabled is False
    assert home not in info.reason and "~" in info.reason


# --- demonstration cases -------------------------------------------------------------


def test_missing_case_file_is_an_empty_allowlist(tmp_path):
    registry = build_registry(tmp_path / "absent.json")
    assert registry.list_cases() == []
    assert registry.get_case("demo") is None


@pytest.mark.parametrize("wrap", [False, True])
def test_case_file_as_list_or_object(tmp_path, wrap):
    items = [case("one"), case("two", title="Second")]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": items} if wrap else items), encoding="utf-8")
    registry = build_registry(path)
    assert [c.case_id for c in registry.list_cases()] == ["one", "two"]
    assert registry.get_case("two").title == "Second"
    assert registry.get_case("three") is None


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        json.dumps({"items": []}),
        json.dumps([case("one"), case("one")]),
        json.dumps([{**case("one"), "unknown_field": 1}]),
        json.dumps([case("Bad ID")]),
        json.dumps([case("one"), case("two", task_type="other_task")]),
    ],
    ids=["invalid-json", "no-cases", "duplicate", "extra-field", "bad-id", "other-task"],
)
def test_invalid_case_file_is_unavailable(tmp_path, content):
    path = tmp_path / "cases.json"
    path.write_text(content, encoding="utf-8")
    registry = build_registry(path)
    assert isinstance(registry, UnavailableCaseRegistry)
    with pytest.raises(CasesUnavailableError):
        registry.list_cases()
    with pytest.raises(CasesUnavailableError):
        registry.get_case("one")


def test_registry_needs_the_verification_package(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, components.VERIFICATION_MODULE, None)
    registry = build_registry(tmp_path / "absent.json")
    assert isinstance(registry, UnavailableCaseRegistry)
    assert "not available" in registry.reason


def test_registry_comes_from_the_verification_package(monkeypatch, tmp_path):
    calls = []

    class CaseRegistry:
        @classmethod
        def from_file(cls, path):
            calls.append(path)
            return cls()

    fake_module(monkeypatch, components.VERIFICATION_MODULE, CaseRegistry=CaseRegistry)
    path = tmp_path / "cases.json"
    assert isinstance(build_registry(path), CaseRegistry)
    assert calls == [path]


def test_demo_cases_path_is_inside_the_package():
    assert components.DEMO_CASES_PATH.parts[-3:] == ("refactor_ai", "fixtures", "demo_cases.json")


def test_repository_demo_cases_load_when_present():
    if not components.DEMO_CASES_PATH.is_file():
        pytest.skip("src/refactor_ai/fixtures/demo_cases.json is not written yet")
    registry = build_registry()
    assert not isinstance(registry, UnavailableCaseRegistry), registry.reason
    for item in registry.list_cases():
        assert item.task_type == "guard_clauses"


def test_as_registry_accepts_objects_and_iterables():
    reference = ReferenceCase.model_validate(case())
    registry = as_registry([reference])
    assert isinstance(registry, StaticCaseRegistry)
    assert registry.get_case("demo") == reference
    assert as_registry(registry) is registry
    with pytest.raises(ValueError):
        StaticCaseRegistry([reference, reference])


# --- workflow ------------------------------------------------------------------------


def test_missing_workflow_fails_runs_clearly(monkeypatch):
    monkeypatch.setitem(sys.modules, components.WORKFLOW_MODULE, None)
    workflow = build_workflow()
    outcome = workflow(
        WorkflowRequest(code=CODE, task_type="guard_clauses"),
        provider=FakeProvider(),
        settings=WorkflowSettings(),
    )
    assert outcome.status == RunStatus.FAILED
    assert outcome.provider_mode == ProviderMode.FAKE
    assert outcome.error.code == "workflow_unavailable"
    assert outcome.call_count == 0


def test_workflow_is_imported_from_the_coordinator(monkeypatch):
    def run_workflow(request, *, provider, settings, runner=None, on_status=None):
        raise AssertionError("not called here")

    fake_module(monkeypatch, components.WORKFLOW_MODULE, run_workflow=run_workflow)
    assert build_workflow() is run_workflow


def test_broken_coordinator_module_is_reported(monkeypatch):
    fake_module(monkeypatch, components.WORKFLOW_MODULE)  # no run_workflow attribute
    outcome = build_workflow()(
        WorkflowRequest(code=CODE, task_type="guard_clauses"),
        provider=FakeProvider(),
        settings=WorkflowSettings(),
    )
    assert outcome.error.code == "workflow_unavailable"
    assert "AttributeError" in outcome.error.message


# --- host-path hygiene ---------------------------------------------------------------


def test_redact_host_paths_handles_both_separators_and_case():
    home = str(Path.home())
    text = f"a {home}\\x b {home.replace(chr(92), '/')}/y c {home.upper()}\\z"
    redacted = redact_host_paths(text)
    assert home not in redacted and home.upper() not in redacted
    assert redacted.count("~") == 3


def test_describe_exception_is_bounded():
    assert describe_exception(ValueError()) == "ValueError"
    assert describe_exception(ValueError("a\n  b")) == "ValueError: a b"
    long = describe_exception(RuntimeError("x" * 1000))
    assert len(long) == components.MAX_REASON_CHARS and long.endswith("...")


# --- adapter requests and model warm-up ----------------------------------------------


class InfoProvider:
    def __init__(self, info=None, error=None):
        self._info = info
        self._error = error

    @property
    def mode(self):
        return ProviderMode.LOCAL_MODEL

    def info(self):
        if self._error is not None:
            raise self._error
        return self._info


LOCAL = ProviderInfo(
    provider_mode=ProviderMode.LOCAL_MODEL, model_id="m", model_revision="r", ready=True
)


def test_adapter_problem_reads_the_configured_adapter():
    with_adapter = LOCAL.model_copy(update={"adapter_id": "lora-1"})
    assert adapter_problem(InfoProvider(with_adapter)) is None
    assert adapter_problem(InfoProvider(LOCAL)) == ADAPTER_MISSING_REASON
    assert adapter_problem(FakeProvider()) == ADAPTER_MISSING_REASON
    assert adapter_problem(InfoProvider({"adapter_id": "lora-1"})) is None
    # Unknown state: the workflow's own adapter check still prevents a silent fallback.
    assert adapter_problem(InfoProvider(error=RuntimeError("down"))) is None


def test_health_info_states_a_missing_adapter_plainly():
    shown = provider_health_info(LOCAL, use_adapter=True, warming_up=False)
    assert shown.ready is False
    assert shown.detail == ADAPTER_MISSING_REASON
    assert provider_health_info(LOCAL, use_adapter=False, warming_up=False) == LOCAL
    with_detail = LOCAL.model_copy(update={"detail": "Model loaded."})
    shown = provider_health_info(with_detail, use_adapter=True, warming_up=False)
    assert shown.detail == f"{ADAPTER_MISSING_REASON} Model loaded."
    with_adapter = with_detail.model_copy(update={"adapter_id": "lora-1"})
    assert provider_health_info(with_adapter, use_adapter=True, warming_up=False) == with_adapter


def test_health_info_reports_a_model_loading_in_the_background():
    loading = LOCAL.model_copy(update={"ready": False, "detail": "Worker not started."})
    shown = provider_health_info(loading, use_adapter=False, warming_up=True)
    assert (shown.ready, shown.detail) == (False, MODEL_LOADING_DETAIL)
    # Once the model reports ready, the provider's own detail is shown again.
    loaded = LOCAL.model_copy(update={"detail": "Model loaded in 3.0 s."})
    assert provider_health_info(loaded, use_adapter=False, warming_up=True) == loaded


class WarmingProvider(InfoProvider):
    def __init__(self, error=None):
        super().__init__(LOCAL)
        self.release = threading.Event()
        self.calls = 0
        self.error = error

    def warm_up(self):
        self.calls += 1
        assert self.release.wait(5)
        if self.error is not None:
            raise self.error
        return LOCAL


def test_warm_up_runs_once_in_the_background():
    provider = WarmingProvider()
    warmup = ProviderWarmup(provider)
    assert warmup.supported
    started = time.monotonic()
    assert warmup.start() is True
    try:
        assert time.monotonic() - started < 0.5
        assert warmup.in_progress and not warmup.wait(0.05)
    finally:
        provider.release.set()
    assert warmup.wait(5) and warmup.join(5)
    assert not warmup.in_progress
    assert provider.calls == 1


def test_warm_up_failure_is_logged_not_raised(caplog):
    provider = WarmingProvider(error=RuntimeError("load failed"))
    provider.release.set()
    warmup = ProviderWarmup(provider)
    warmup.start()
    assert warmup.wait(5) and warmup.join(5)
    assert "warm-up failed" in caplog.text


def test_providers_without_warm_up_are_ready_at_once():
    warmup = ProviderWarmup(FakeProvider())
    assert warmup.supported is False
    assert warmup.start() is False
    assert warmup.wait(0) and not warmup.in_progress and warmup.join(0)


def test_real_local_provider_has_warm_up():
    local = pytest.importorskip("refactor_ai.providers.local")
    assert callable(getattr(local.LocalProvider, "warm_up", None))

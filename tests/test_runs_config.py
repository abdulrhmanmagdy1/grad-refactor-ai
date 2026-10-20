"""REFACTOR_AI_* settings: documented defaults, parsing and validation."""

import dataclasses
from pathlib import Path

import pytest

from refactor_ai.config import ConfigError, Settings


def test_documented_defaults():
    settings = Settings.from_env({})
    assert settings.provider == "fake"
    assert settings.local_model_config == Path("configs/model.local.json")
    assert settings.db_path == Path("runs/app/runs.sqlite3")
    assert settings.runner == "auto"
    assert settings.max_pending == 4
    assert settings.retention == 200
    assert settings.frontend_dist == Path("frontend/dist")
    assert settings.refactor_use_adapter is False
    assert Settings() == settings


def test_every_variable_is_read():
    settings = Settings.from_env(
        {
            "REFACTOR_AI_PROVIDER": "local",
            "REFACTOR_AI_MODEL_CONFIG": "configs/other.json",
            "REFACTOR_AI_DB": "data/history.sqlite3",
            "REFACTOR_AI_RUNNER": "disabled",
            "REFACTOR_AI_MAX_PENDING": "9",
            "REFACTOR_AI_RETENTION": "50",
            "REFACTOR_AI_REFACTOR_USE_ADAPTER": "true",
        }
    )
    assert settings.provider == "local"
    assert settings.local_model_config == Path("configs/other.json")
    assert settings.db_path == Path("data/history.sqlite3")
    assert settings.runner == "disabled"
    assert (settings.max_pending, settings.retention) == (9, 50)
    assert settings.refactor_use_adapter is True


def test_values_are_trimmed_and_case_insensitive():
    settings = Settings.from_env(
        {
            "REFACTOR_AI_PROVIDER": "  LOCAL ",
            "REFACTOR_AI_RUNNER": "Disabled",
            "REFACTOR_AI_MAX_PENDING": " 2 ",
        }
    )
    assert (settings.provider, settings.runner, settings.max_pending) == ("local", "disabled", 2)


def test_empty_values_keep_defaults():
    names = (
        "REFACTOR_AI_PROVIDER",
        "REFACTOR_AI_MODEL_CONFIG",
        "REFACTOR_AI_DB",
        "REFACTOR_AI_RUNNER",
        "REFACTOR_AI_MAX_PENDING",
        "REFACTOR_AI_RETENTION",
        "REFACTOR_AI_REFACTOR_USE_ADAPTER",
    )
    assert Settings.from_env(dict.fromkeys(names, "  ")) == Settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("REFACTOR_AI_PROVIDER", "gpu"),
        ("REFACTOR_AI_PROVIDER", "local_model"),
        ("REFACTOR_AI_RUNNER", "on"),
        ("REFACTOR_AI_MAX_PENDING", "0"),
        ("REFACTOR_AI_MAX_PENDING", "101"),
        ("REFACTOR_AI_MAX_PENDING", "-1"),
        ("REFACTOR_AI_MAX_PENDING", "four"),
        ("REFACTOR_AI_MAX_PENDING", "4.5"),
        ("REFACTOR_AI_MAX_PENDING", "1_000"),
        ("REFACTOR_AI_RETENTION", "0"),
        ("REFACTOR_AI_RETENTION", "100001"),
        ("REFACTOR_AI_RETENTION", "1e3"),
        ("REFACTOR_AI_REFACTOR_USE_ADAPTER", "maybe"),
        ("REFACTOR_AI_REFACTOR_USE_ADAPTER", "2"),
        ("REFACTOR_AI_REFACTOR_USE_ADAPTER", "enabled"),
    ],
)
def test_invalid_values_name_the_variable(name, value):
    with pytest.raises(ConfigError, match=name):
        Settings.from_env({name: value})


def test_bounds_are_inclusive():
    low = Settings.from_env({"REFACTOR_AI_MAX_PENDING": "1", "REFACTOR_AI_RETENTION": "1"})
    high = Settings.from_env({"REFACTOR_AI_MAX_PENDING": "100", "REFACTOR_AI_RETENTION": "100000"})
    assert (low.max_pending, low.retention) == (1, 1)
    assert (high.max_pending, high.retention) == (100, 100000)


def test_direct_construction_is_validated_and_frozen(tmp_path):
    with pytest.raises(ConfigError):
        Settings(max_pending=True)
    with pytest.raises(ConfigError):
        Settings(retention="5")
    with pytest.raises(ConfigError):
        Settings(db_path="")
    with pytest.raises(ConfigError):
        Settings(shutdown_grace_s=-1)
    settings = Settings(db_path=str(tmp_path / "x.sqlite3"), frontend_dist=str(tmp_path))
    assert isinstance(settings.db_path, Path) and isinstance(settings.frontend_dist, Path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.provider = "local"


def test_reads_the_process_environment(monkeypatch):
    monkeypatch.setenv("REFACTOR_AI_RETENTION", "17")
    assert Settings.from_env().retention == 17


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("On", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("OFF", False),
    ],
)
def test_adapter_flag_accepts_common_spellings(value, expected):
    settings = Settings.from_env({"REFACTOR_AI_REFACTOR_USE_ADAPTER": value})
    assert settings.refactor_use_adapter is expected


def test_adapter_flag_must_be_a_boolean_in_code():
    with pytest.raises(ConfigError, match="REFACTOR_AI_REFACTOR_USE_ADAPTER"):
        Settings(refactor_use_adapter="true")

"""Service configuration from the REFACTOR_AI_* environment variables.

Defaults and meanings are documented in docs/architecture/contracts.md. Values are read
once when the service starts; an invalid value stops startup with a message that names
the variable. Empty values count as unset. Relative paths are resolved against the
working directory, so start the service from the repository root.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_PROVIDER = "REFACTOR_AI_PROVIDER"
ENV_MODEL_CONFIG = "REFACTOR_AI_MODEL_CONFIG"
ENV_DB = "REFACTOR_AI_DB"
ENV_RUNNER = "REFACTOR_AI_RUNNER"
ENV_MAX_PENDING = "REFACTOR_AI_MAX_PENDING"
ENV_RETENTION = "REFACTOR_AI_RETENTION"
ENV_REFACTOR_USE_ADAPTER = "REFACTOR_AI_REFACTOR_USE_ADAPTER"
ENV_PROJECT_MODEL_CONFIG = "REFACTOR_AI_PROJECT_MODEL_CONFIG"
ENV_PROJECT_TESTS = "REFACTOR_AI_PROJECT_TESTS"

PROVIDERS = ("fake", "local")
RUNNER_MODES = ("auto", "disabled")
MAX_PENDING_RANGE = (1, 100)
RETENTION_RANGE = (1, 100_000)

_INTEGER = re.compile(r"[+-]?[0-9]+")
_TRUE = frozenset({"true", "1", "yes", "on"})
_FALSE = frozenset({"false", "0", "no", "off"})


class ConfigError(ValueError):
    """A configuration value is invalid; the message names the variable."""


@dataclass(frozen=True)
class Settings:
    """Validated service settings.

    provider: "fake" (deterministic test provider, the default) or "local" (the pinned
    local model through refactor_ai.providers.local). runner: "auto" lets the reference
    runner execute trusted tests only when its isolation checks pass; "disabled" forces
    not_run. max_pending bounds unfinished runs (waiting plus the one running).
    retention caps stored runs. refactor_use_adapter runs the refactoring role with the
    provider's LoRA adapter (arms C/D); without a configured adapter runs fail instead of
    using the base model. project_model_config is the GGUF model of the project review mode
    (used with provider=local when the file exists). project_tests allows a project review to
    run the uploaded project's own tests when the person asks for it; it is off by default
    because those tests execute the uploaded code on this machine. frontend_dist and
    shutdown_grace_s have no environment variables.
    """

    provider: str = "fake"
    local_model_config: Path = Path("configs/model.local.json")
    db_path: Path = Path("runs/app/runs.sqlite3")
    runner: str = "auto"
    max_pending: int = 4
    retention: int = 200
    frontend_dist: Path | None = Path("frontend/dist")
    refactor_use_adapter: bool = False
    shutdown_grace_s: float = 10.0
    project_model_config: Path = Path("configs/model.project.local.json")
    project_tests: bool = False

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise ConfigError(f"{ENV_PROVIDER} must be 'fake' or 'local', got {self.provider!r}")
        if self.runner not in RUNNER_MODES:
            raise ConfigError(f"{ENV_RUNNER} must be 'auto' or 'disabled', got {self.runner!r}")
        _check_int(ENV_MAX_PENDING, self.max_pending, *MAX_PENDING_RANGE)
        _check_int(ENV_RETENTION, self.retention, *RETENTION_RANGE)
        for name, env in (
            ("local_model_config", ENV_MODEL_CONFIG),
            ("db_path", ENV_DB),
            ("project_model_config", ENV_PROJECT_MODEL_CONFIG),
        ):
            value = getattr(self, name)
            if not str(value).strip():
                raise ConfigError(f"{env} must not be empty")
            object.__setattr__(self, name, Path(value))
        if self.frontend_dist is not None:
            object.__setattr__(self, "frontend_dist", Path(self.frontend_dist))
        if not isinstance(self.refactor_use_adapter, bool):
            raise ConfigError(f"{ENV_REFACTOR_USE_ADAPTER} must be true or false")
        if not isinstance(self.project_tests, bool):
            raise ConfigError(f"{ENV_PROJECT_TESTS} must be true or false")
        if not 0 <= float(self.shutdown_grace_s) <= 600:
            raise ConfigError("shutdown_grace_s must be between 0 and 600 seconds")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read the documented variables; unset or empty variables keep their defaults."""
        env = os.environ if environ is None else environ
        values: dict[str, object] = {}
        if (value := _get(env, ENV_PROVIDER)) is not None:
            values["provider"] = value.lower()
        if (value := _get(env, ENV_MODEL_CONFIG)) is not None:
            values["local_model_config"] = Path(value)
        if (value := _get(env, ENV_DB)) is not None:
            values["db_path"] = Path(value)
        if (value := _get(env, ENV_RUNNER)) is not None:
            values["runner"] = value.lower()
        if (value := _get(env, ENV_MAX_PENDING)) is not None:
            values["max_pending"] = _parse_int(ENV_MAX_PENDING, value)
        if (value := _get(env, ENV_RETENTION)) is not None:
            values["retention"] = _parse_int(ENV_RETENTION, value)
        if (value := _get(env, ENV_REFACTOR_USE_ADAPTER)) is not None:
            values["refactor_use_adapter"] = _parse_bool(ENV_REFACTOR_USE_ADAPTER, value)
        if (value := _get(env, ENV_PROJECT_MODEL_CONFIG)) is not None:
            values["project_model_config"] = Path(value)
        if (value := _get(env, ENV_PROJECT_TESTS)) is not None:
            values["project_tests"] = _parse_bool(ENV_PROJECT_TESTS, value)
        return cls(**values)

    @property
    def projects_db_path(self) -> Path:
        """Project review records, next to the run history."""
        return self.db_path.with_name("projects.sqlite3")

    @property
    def projects_dir(self) -> Path:
        """Uploaded project files, one folder per review."""
        return self.db_path.parent / "projects"


def _get(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _parse_int(name: str, value: str) -> int:
    if not _INTEGER.fullmatch(value):
        raise ConfigError(f"{name} must be a whole number, got {value!r}")
    return int(value)


def _parse_bool(name: str, value: str) -> bool:
    lowered = value.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ConfigError(f"{name} must be true or false, got {value!r}")


def _check_int(name: str, value: object, low: int, high: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be a whole number, got {value!r}")
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}, got {value}")

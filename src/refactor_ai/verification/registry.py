"""Server-owned allowlist of demonstration reference cases.

Cases come only from src/refactor_ai/fixtures/demo_cases.json (written by the data
workstream): a JSON list of ReferenceCase objects, or an object with that list under
"cases". Every entry is validated with the Pydantic model; ids must be unique and the
task type must be the supported one. A missing file is an empty allowlist; an invalid
file raises RegistryError instead of silently dropping cases. Callers choose a case by
id only; they never supply paths, tests or code to run.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from refactor_ai.contracts import ReferenceCase, ReferenceCaseSummary
from refactor_ai.tasks import guard_clauses

DEFAULT_CASES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "demo_cases.json"


class RegistryError(ValueError):
    """The demonstration case file exists but is not a valid allowlist."""


def normalize_newlines(code: str) -> str:
    return code.replace("\r\n", "\n").replace("\r", "\n")


def code_matches_case(code: str, case: ReferenceCase) -> bool:
    """Equal after newline normalization, ignoring trailing whitespace at the end (the
    rule the API uses for reference_case_mismatch)."""
    return normalize_newlines(code).rstrip() == normalize_newlines(case.original_code).rstrip()


def load_cases(path: str | Path | None = None) -> list[ReferenceCase]:
    """Validated cases from the file; [] when the file does not exist."""
    file = Path(path) if path is not None else DEFAULT_CASES_PATH
    if not file.is_file():
        return []
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise RegistryError(f"{file.name} is not readable JSON: {exc}") from exc
    items = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise RegistryError(f"{file.name} must hold a list of reference cases")
    cases: list[ReferenceCase] = []
    for position, item in enumerate(items):
        try:
            cases.append(ReferenceCase.model_validate(item))
        except ValidationError as exc:
            raise RegistryError(f"{file.name}: case {position} is invalid: {exc}") from exc
    _validate(cases, file.name)
    return cases


def _validate(cases: Iterable[ReferenceCase], source: str) -> None:
    seen: set[str] = set()
    for case in cases:
        if case.case_id in seen:
            raise RegistryError(f"{source}: duplicate case id {case.case_id!r}")
        seen.add(case.case_id)
        if case.task_type != guard_clauses.TASK_TYPE:
            raise RegistryError(
                f"{source}: case {case.case_id!r} has unsupported task type {case.task_type!r}"
            )
        if not case.function_name.isidentifier():
            raise RegistryError(f"{source}: case {case.case_id!r} has an invalid function name")


class CaseRegistry:
    """Read-only allowlist; lookups return copies so callers cannot change the cases."""

    def __init__(self, cases: Iterable[ReferenceCase] = ()) -> None:
        items = list(cases)
        _validate(items, "registry")
        self._cases = {case.case_id: case.model_copy(deep=True) for case in items}

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> CaseRegistry:
        return cls(load_cases(path))

    def __len__(self) -> int:
        return len(self._cases)

    def __contains__(self, case_id: object) -> bool:
        return case_id in self._cases

    def list_cases(self) -> list[ReferenceCase]:
        return [case.model_copy(deep=True) for case in self._cases.values()]

    def get_case(self, case_id: str) -> ReferenceCase | None:
        case = self._cases.get(case_id)
        return None if case is None else case.model_copy(deep=True)

    def summaries(self) -> list[ReferenceCaseSummary]:
        return [
            ReferenceCaseSummary(
                case_id=case.case_id,
                title=case.title,
                function_name=case.function_name,
                code=case.original_code,
                test_count=len(case.tests),
            )
            for case in self._cases.values()
        ]

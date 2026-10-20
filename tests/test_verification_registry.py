import ast
import json

import pytest

from refactor_ai.contracts import ReferenceCase, ReferenceCaseSummary
from refactor_ai.tasks import guard_clauses
from refactor_ai.verification import registry
from refactor_ai.verification.registry import CaseRegistry, RegistryError, code_matches_case

CODE = "def f(x):\n    if x:\n        return 1\n    else:\n        return 2\n"


def case_data(case_id="demo-1", **overrides):
    data = {
        "case_id": case_id,
        "task_type": "guard_clauses",
        "title": "Demo",
        "function_name": "f",
        "original_code": CODE,
        "tests": [{"args": "[1]", "expect": {"kind": "return", "value": "1"}}],
    }
    data.update(overrides)
    return data


def write(tmp_path, content):
    path = tmp_path / "demo_cases.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


def test_missing_file_is_an_empty_allowlist(tmp_path):
    assert registry.load_cases(tmp_path / "absent.json") == []
    assert len(CaseRegistry.from_file(tmp_path / "absent.json")) == 0


@pytest.mark.parametrize("wrap", [False, True])
def test_valid_file_loads(tmp_path, wrap):
    items = [case_data("demo-1"), case_data("demo-2", title=None)]
    path = write(tmp_path, {"cases": items} if wrap else items)
    cases = registry.load_cases(path)
    assert [case.case_id for case in cases] == ["demo-1", "demo-2"]
    assert all(isinstance(case, ReferenceCase) for case in cases)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "not readable JSON"),
        ({"items": []}, "must hold a list"),
        ("42", "must hold a list"),
        ([case_data(case_id="Bad Id")], "case 0 is invalid"),
        ([case_data(), {"case_id": "x"}], "case 1 is invalid"),
        ([case_data(unexpected=True)], "case 0 is invalid"),
        ([case_data("same"), case_data("same")], "duplicate case id 'same'"),
        ([case_data(task_type="extract_method")], "unsupported task type"),
        ([case_data(function_name="not valid")], "invalid function name"),
    ],
)
def test_invalid_files_are_rejected(tmp_path, content, message):
    path = write(tmp_path, content)
    with pytest.raises(RegistryError, match=message):
        registry.load_cases(path)


def test_lookup_returns_copies(tmp_path):
    allowlist = CaseRegistry.from_file(write(tmp_path, [case_data()]))
    first = allowlist.get_case("demo-1")
    first.tests.clear()
    first.original_code = "changed"
    again = allowlist.get_case("demo-1")
    assert again.original_code == CODE and len(again.tests) == 1
    listed = allowlist.list_cases()
    listed[0].tests.clear()
    assert len(allowlist.list_cases()[0].tests) == 1


def test_unknown_case_is_none():
    allowlist = CaseRegistry([ReferenceCase.model_validate(case_data())])
    assert allowlist.get_case("missing") is None
    assert "demo-1" in allowlist and "missing" not in allowlist


def test_registry_rejects_duplicates_in_memory():
    case = ReferenceCase.model_validate(case_data())
    with pytest.raises(RegistryError):
        CaseRegistry([case, case])


def test_summaries():
    allowlist = CaseRegistry([ReferenceCase.model_validate(case_data())])
    assert allowlist.summaries() == [
        ReferenceCaseSummary(
            case_id="demo-1", title="Demo", function_name="f", code=CODE, test_count=1
        )
    ]


@pytest.mark.parametrize(
    ("code", "matches"),
    [
        (CODE, True),
        (CODE.replace("\n", "\r\n"), True),
        (CODE.rstrip("\n"), True),
        (CODE + "\n\n   ", True),
        (CODE.replace("return 2", "return 3"), False),
        ("  " + CODE, False),
    ],
)
def test_code_matches_case(code, matches):
    assert code_matches_case(code, ReferenceCase.model_validate(case_data())) is matches


def test_shipped_demonstration_cases_load():
    """The allowlist the API serves: src/refactor_ai/fixtures/demo_cases.json."""
    assert registry.DEFAULT_CASES_PATH.is_file()
    cases = registry.load_cases()
    allowlist = CaseRegistry.from_file()
    assert cases and len(allowlist) == len(cases)
    assert len({case.case_id for case in cases}) == len(cases)
    for case in cases:
        assert case.task_type == "guard_clauses"
        assert case.tests, case.case_id
        assert case.reference_code, case.case_id
        func, reason = guard_clauses.parse_function(case.original_code)
        assert reason is None and func.name == case.function_name, case.case_id
        assert code_matches_case(case.original_code, allowlist.get_case(case.case_id))
        for test in case.tests:  # every literal must be readable by the runner
            ast.literal_eval(test.args)
            ast.literal_eval(test.kwargs)
            if test.expect.kind == "return":
                ast.literal_eval(test.expect.value)
            else:
                assert test.expect.exception
    summaries = {summary.case_id: summary for summary in allowlist.summaries()}
    assert {case.case_id: len(case.tests) for case in cases} == {
        case_id: summary.test_count for case_id, summary in summaries.items()
    }

import json

import pytest

from refactor_ai.agents import parsing
from refactor_ai.contracts import ReviewVerdict


def finding(start=2, end=5, kind="nested_conditional", reason="Else branch returns.", **extra):
    return {"type": kind, "start_line": start, "end_line": end, "reason": reason, **extra}


def analysis(findings=None, supported=True, **extra):
    return json.dumps(
        {
            "supported_task": supported,
            "findings": [finding()] if findings is None else findings,
            "unsupported_reason": None,
            **extra,
        }
    )


# --- Helpers -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('Here: {"a": {"b": 2}} done', '{"a": {"b": 2}}'),
        ('{"text": "a } inside", "n": 1} tail', '{"text": "a } inside", "n": 1}'),
        ('{"quote": "say \\"}\\" now"}', '{"quote": "say \\"}\\" now"}'),
        ('{ {"inner": 1}', '{"inner": 1}'),
        ("no object here", None),
        ('{"unbalanced": 1', None),
    ],
)
def test_first_json_object(text, expected):
    assert parsing.first_json_object(text) == expected


def test_strip_code_fence():
    assert parsing.strip_code_fence('```json\n{"a": 1}\n```') == ('{"a": 1}\n', True)
    assert parsing.strip_code_fence('```\n{"a": 1}') == ('{"a": 1}', True)
    assert parsing.strip_code_fence('{"a": 1}') == ('{"a": 1}', False)


def test_strip_code_fence_only_removes_a_fence_around_the_whole_text():
    inner = '{"s": "```python\\nx\\n```"}'
    assert parsing.strip_code_fence(f"```json\n{inner}\n```") == (f"{inner}\n", True)
    trailing = '{"a": 1}\n```\ndef f(x):\n    return x\n```'
    assert parsing.strip_code_fence(trailing) == (trailing, False)
    assert parsing.strip_code_fence('```python\n{"a": 1}\n```\nDone.') == (
        '{"a": 1}\n```\nDone.',
        True,
    )


# --- Analysis ------------------------------------------------------------------------


def test_strict_analysis_is_accepted_without_repair():
    result = parsing.parse_analysis(analysis(), line_count=9)
    assert result.error is None and not result.repaired and result.repairs == []
    assert result.report.source == "model" and result.report.supported_task is True
    assert [(f.start_line, f.end_line) for f in result.report.findings] == [(2, 5)]
    assert result.dropped == []


def test_application_fields_written_by_the_model_are_ignored():
    text = analysis(schema_version=7, source="static")
    result = parsing.parse_analysis(text, line_count=9)
    assert result.report.schema_version == 1 and result.report.source == "model"


@pytest.mark.parametrize(
    ("text", "repairs"),
    [
        (f"```json\n{analysis()}\n```", ["code_fence_removed"]),
        (f"```\n{analysis()}\n```", ["code_fence_removed"]),
        (f"Here is my analysis:\n{analysis()}\nHope it helps.", ["json_object_extracted"]),
        # A fence that does not start the output is not a surrounding fence; the object
        # is extracted from the text as a whole.
        (f"Result:\n```json\n{analysis()}\n```", ["json_object_extracted"]),
        (f"Lines {{2-5}}:\n```json\n{analysis()}\n```", ["json_object_extracted"]),
        (f"{analysis()}\n```\ndef f(x):\n    return x\n```", ["json_object_extracted"]),
        (f"```python\n{analysis()}\n```\nDone.", ["code_fence_removed", "json_object_extracted"]),
        (f"```json\n{analysis()}", ["code_fence_removed"]),
        (
            f"```json\nAnswer: {analysis()} end\n```",
            ["code_fence_removed", "json_object_extracted"],
        ),
    ],
)
def test_one_deterministic_repair(text, repairs):
    result = parsing.parse_analysis(text, line_count=9)
    assert result.error is None, result.error
    assert result.repaired is True and result.repairs == repairs
    assert len(result.report.findings) == 1


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty output"),
        ("   \n", "empty output"),
        ("I found nothing.", "no JSON object found"),
        ('{"supported_task": true, "findings": [', "no JSON object found"),
        ("[1, 2]", "not an object"),
        ('{"supported_task": "true", "findings": []}', "supported_task must be"),
        ('{"supported_task": 1, "findings": []}', "supported_task must be"),
        ('{"supported_task": true, "findings": {}}', "findings must be a list"),
        ('{"supported_task": true, "findings": [], "unsupported_reason": 3}', "must be a string"),
        ('{"supported_task": true, "findings": [], "confidence": 0.9}', "unexpected keys"),
        ('{"findings": []}', "supported_task must be"),
        ("{'supported_task': True, 'findings': []}", "invalid JSON"),
    ],
)
def test_invalid_analysis_reports_an_error(text, message):
    result = parsing.parse_analysis(text, line_count=9)
    assert result.report is None
    assert message in result.error


def test_repair_that_changes_nothing_reports_the_strict_error():
    result = parsing.parse_analysis('{"supported_task": true, "extra": 1}', line_count=9)
    assert result.report is None and result.repaired is False
    assert "unexpected keys: extra" in result.error


def test_invalid_after_repair_is_an_error():
    result = parsing.parse_analysis('Answer: {"supported_task": "no"}', line_count=9)
    assert result.report is None and result.repaired is True
    assert "supported_task must be" in result.error


@pytest.mark.parametrize(
    ("item", "why"),
    [
        (finding(start=8, end=12), "outside the input (1-9)"),
        (finding(start=0, end=2), "does not match the schema"),
        (finding(start=5, end=4), "does not match the schema"),
        (finding(start="2"), "does not match the schema"),
        (finding(start=True, end=3), "does not match the schema"),
        (finding(start=2.0), "does not match the schema"),
        (finding(kind="nested_if"), "is not allowed"),
        (finding(kind=""), "does not match the schema"),
        (finding(reason=""), "does not match the schema"),
        (finding(reason="x" * 601), "does not match the schema"),
        (finding(severity="high"), "does not match the schema"),
        ("lines 2-5", "does not match the schema"),
        ({"type": "nested_conditional", "start_line": 2}, "does not match the schema"),
    ],
)
def test_invalid_findings_are_dropped_individually(item, why):
    result = parsing.parse_analysis(analysis([finding(), item]), line_count=9)
    assert result.error is None
    assert len(result.report.findings) == 1
    assert len(result.dropped) == 1 and why in result.dropped[0]
    assert result.dropped[0].startswith("finding 1 ")


def test_findings_are_limited_to_twenty():
    items = [finding(start=1, end=2, reason=f"r{index}") for index in range(23)]
    result = parsing.parse_analysis(analysis(items), line_count=9)
    assert len(result.report.findings) == 20
    assert len(result.dropped) == 3 and "limit of 20" in result.dropped[0]


def test_line_limit_is_inclusive():
    result = parsing.parse_analysis(analysis([finding(start=9, end=9)]), line_count=9)
    assert result.dropped == [] and len(result.report.findings) == 1


def test_unsupported_report_without_findings_parses():
    text = json.dumps(
        {"supported_task": False, "findings": [], "unsupported_reason": "Nothing to flatten."}
    )
    result = parsing.parse_analysis(text, line_count=3)
    assert result.report.supported_task is False
    assert result.report.unsupported_reason == "Nothing to flatten."


# --- Review --------------------------------------------------------------------------


def review(verdict="accept", reasons=None, suggestion=None, **extra):
    return json.dumps(
        {
            "verdict": verdict,
            "reasons": ["Same behavior."] if reasons is None else reasons,
            "suggested_correction": suggestion,
            **extra,
        }
    )


@pytest.mark.parametrize("verdict", ["accept", "reject", "uncertain"])
def test_strict_review(verdict):
    result = parsing.parse_review(
        review(verdict, suggestion="Use <=." if verdict == "reject" else None)
    )
    assert result.error is None and result.repaired is False
    assert result.result.verdict == ReviewVerdict(verdict)
    assert result.result.reasons == ["Same behavior."]


def test_review_defaults_and_application_fields():
    result = parsing.parse_review('{"verdict": "accept", "schema_version": 9}')
    assert result.result.reasons == [] and result.result.suggested_correction is None
    assert result.result.schema_version == 1


@pytest.mark.parametrize(
    ("text", "verdict", "repairs"),
    [
        (review("Accept"), "accept", ["verdict_case_normalized"]),
        (review(" REJECT "), "reject", ["verdict_case_normalized"]),
        (f"```json\n{review()}\n```", "accept", ["code_fence_removed"]),
        (f"My verdict: {review('uncertain')}", "uncertain", ["json_object_extracted"]),
        (
            f"```json\n{review('Uncertain')}\n```",
            "uncertain",
            ["code_fence_removed", "verdict_case_normalized"],
        ),
    ],
)
def test_review_repair(text, verdict, repairs):
    result = parsing.parse_review(text)
    assert result.error is None, result.error
    assert result.repaired is True and result.repairs == repairs
    assert result.result.verdict.value == verdict


FENCED_SUGGESTION = "```python\nif weight <= 0:\n    raise ValueError('x')\n```"
DICT_BLOCK = '```\ndef f(x):\n    return {"x": 1}\n```'


@pytest.mark.parametrize(
    ("text", "repairs"),
    [
        # A ``` inside a string value does not close the surrounding fence.
        (
            f"```json\n{review('reject', suggestion=FENCED_SUGGESTION)}\n```",
            ["code_fence_removed"],
        ),
        # A code block after bare JSON is not a fence around it.
        (f"{review('reject')}\n```\ndef f(x):\n    return x\n```", ["json_object_extracted"]),
        (f"{review('reject')}\n{DICT_BLOCK}", ["json_object_extracted"]),
        # JSON in a fence with another tag, followed by prose.
        (
            f"```python\n{review('reject')}\n```\nThat is my verdict.",
            ["code_fence_removed", "json_object_extracted"],
        ),
        # Braces in prose before the JSON are skipped when they are not valid JSON.
        (f"Checked {{weight}}:\n```json\n{review('reject')}\n```", ["json_object_extracted"]),
    ],
)
def test_review_json_next_to_other_fences_is_not_lost(text, repairs):
    result = parsing.parse_review(text)
    assert result.error is None, result.error
    assert result.result.verdict == ReviewVerdict.REJECT
    assert result.repaired is True and result.repairs == repairs
    if "raise ValueError" in text:
        assert result.result.suggested_correction == FENCED_SUGGESTION


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty output"),
        ("Looks good to me.", "no JSON object found"),
        (review("maybe"), "schema mismatch"),
        (review("approve"), "schema mismatch"),
        ('{"reasons": []}', "verdict is missing"),
        (review(reasons="fine"), "schema mismatch"),
        (review(reasons=[1, 2]), "schema mismatch"),
        (review(reasons=[f"r{index}" for index in range(11)]), "schema mismatch"),
        (review(suggestion=["x"]), "schema mismatch"),
        (review(confidence=0.9), "unexpected keys: confidence"),
        ('["accept"]', "not an object"),
        ('{"verdict": "accept"', "no JSON object found"),
        ('{"verdict": true}', "schema mismatch"),
    ],
)
def test_invalid_review_is_an_error(text, message):
    result = parsing.parse_review(text)
    assert result.result is None
    assert message in result.error, result.error


def test_deeply_nested_json_is_a_parse_error_not_a_crash():
    deep = "[" * 100_000 + "]" * 100_000
    assert "recursion" in parsing.parse_analysis(deep, line_count=9).error
    assert parsing.parse_review(deep).result is None
    nested = '{"verdict": ' + "[" * 100_000 + "]" * 100_000 + "}"
    assert parsing.parse_analysis(nested, line_count=9).report is None
    assert parsing.parse_review(nested).result is None


def test_review_parsing_never_guesses_a_verdict():
    for text in ("ACCEPT", "accept", "The verdict is accept."):
        assert parsing.parse_review(text).result is None


def test_an_object_inside_invalid_json_is_not_used():
    text = '{verdict: reject, "example": {"verdict": "accept"}}'
    assert parsing.parse_review(text).result is None
    assert parsing.parse_review(f"```json\n{text}\n```").result is None

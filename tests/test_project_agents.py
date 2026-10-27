"""Project review mode: agent prompts and parsers, applying fixes and the static re-check."""

from __future__ import annotations

import textwrap

import pytest

from refactor_ai.project import agents, fixes
from refactor_ai.project.models import Category, Finding, Severity


def code(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


# --- prompts --------------------------------------------------------------------------


def test_numbered_uses_file_line_numbers():
    assert agents.numbered("a = 1\nb = 2\n", 9) == " 9 | a = 1\n10 | b = 2"


def test_prompts_carry_the_code_and_the_known_findings():
    messages = agents.bug_messages("f", "def f():\n    return 1\n", 3, ["line 4: known"])
    assert [m.role for m in messages] == ["system", "user"]
    user = messages[1].content
    assert "3 | def f():" in user and "- line 4: known" in user and '"findings"' in user
    quality = agents.quality_messages("a.py", "x = 1\n", 1, [])
    assert "security|quality" in quality[1].content and "Already reported: nothing." in (
        quality[1].content
    )
    fix = agents.fix_messages("Mutable default", "Shared list.", 7, "def f(x=[]):\n    pass\n")
    assert "(line 7 of the file)" in fix[1].content and "import line before" in fix[1].content
    review = agents.fix_review_messages("t", "p", "--- a\n+++ b\n")
    assert "```diff" in review[1].content and "accept|reject|uncertain" in review[1].content
    assert "Project description" not in user


def test_finders_see_the_project_description_shortened():
    readme = "Fines start the day after the due date. " + "x" * 2000
    for messages in (
        agents.bug_messages("f", "def f():\n    pass\n", 1, [], readme),
        agents.quality_messages("a.py", "x = 1\n", 1, [], readme),
    ):
        user = messages[1].content
        assert user.startswith("Project description (from its README):\nFines start the day")
        assert "x" * agents.MAX_DESCRIPTION not in user and "x" * 700 in user
    assert agents.PROMPT_VERSION == "project-v5"
    assert agents.ELSEWHERE in messages[1].content


def test_judges_give_their_reason_before_the_verdict():
    for messages in (
        agents.check_messages("t", "p", "x = 1\n", 1),
        agents.architecture_check_messages("t", "p", "map"),
        agents.fix_review_messages("t", "p", "--- a\n+++ b\n"),
    ):
        user = messages[1].content
        assert user.index('"reason') < user.index('"verdict"')


# --- parsing --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '{"findings": []}',
        'Here you go:\n```json\n{"findings": []}\n```\nDone.',
        'noise {"findings": []} trailing {"other": 1}',
    ],
)
def test_extract_json_tolerates_fences_and_text(text):
    assert agents.extract_json(text) == {"findings": []}


def test_extract_json_handles_braces_inside_strings_and_failures():
    assert agents.extract_json('{"code": "d = {1: 2}", "n": 1}') == {"code": "d = {1: 2}", "n": 1}
    assert agents.extract_json("no json here") is None
    assert agents.extract_json("[1, 2]") is None


def test_parse_findings_keeps_valid_items_only():
    text = """{"findings": [
        {"line": 3, "code": "x = y", "problem": "y is undefined", "severity": "high"},
        {"line": "4", "code": "z = 1", "problem": "unused", "severity": "extreme"},
        {"line": 5, "code": "", "problem": "no quote"},
        {"line": true, "code": "a", "problem": "bool line"},
        {"code": "b", "problem": "no line"},
        "not an object"
    ]}"""
    parsed = agents.parse_findings(text)
    assert parsed.error is None and not parsed.repaired
    assert [(f["line"], f["severity"]) for f in parsed.items] == [(3, "high"), (4, "medium")]


def test_parse_findings_salvages_a_list_cut_off_by_the_token_limit():
    text = (
        '{"findings": [{"line": 1, "code": "a = 1", "problem": "p1"}, '
        '{"line": 2, "code": "b = 2", "problem": "p2"}, {"line": 3, "code": "c ='
    )
    parsed = agents.parse_findings(text)
    assert parsed.repaired and [f["line"] for f in parsed.items] == [1, 2]
    assert agents.parse_findings("nothing useful").error == "unparseable_output"


def test_parse_findings_with_categories():
    text = """{"findings": [
        {"line": 1, "code": "eval(x)", "category": "security", "problem": "eval",
         "recommendation": "Use ast.literal_eval.", "severity": "high"},
        {"line": 2, "code": "y = 1", "category": "style", "problem": "style"}
    ]}"""
    parsed = agents.parse_findings(text, categories=("security", "quality"))
    assert [(f["category"], f["recommendation"]) for f in parsed.items] == [
        ("security", "Use ast.literal_eval.")
    ]


def test_parse_architecture():
    text = """```json
    {"summary": "Small project.", "issues": [
      {"title": "Cycle", "modules": ["a", "b", 3], "problem": "a and b import each other.",
       "recommendation": "Extract c.", "severity": "high"},
      {"title": "", "modules": ["a"], "problem": "empty title"},
      {"title": "No modules", "modules": "a", "problem": "not a list"}
    ]}
    ```"""
    parsed = agents.parse_architecture(text)
    assert parsed.extra["summary"] == "Small project."
    assert parsed.items == [
        {
            "title": "Cycle",
            "problem": "a and b import each other.",
            "modules": ["a", "b"],
            "recommendation": "Extract c.",
            "severity": "high",
        }
    ]
    assert agents.parse_architecture("garbage").error == "unparseable_output"


@pytest.mark.parametrize(
    ("text", "verdict", "reasons"),
    [
        ('{"verdict": "accept", "reasons": ["fixes it"]}', "accept", ["fixes it"]),
        ('{"verdict": "reject", "reason": "breaks callers"}', "reject", ["breaks callers"]),
        ('{"verdict": "accept", "reasons": "not a list"}', "accept", []),
        ('broken {"verdict": "uncertain", "reasons": [', "uncertain", []),
    ],
)
def test_parse_verdict(text, verdict, reasons):
    parsed = agents.parse_verdict(text, ("accept", "reject", "uncertain"))
    assert parsed.error is None
    assert parsed.extra == {"verdict": verdict, "reasons": reasons}


def test_parse_verdict_errors():
    allowed = ("accept", "reject", "uncertain")
    assert agents.parse_verdict('{"verdict": "maybe"}', allowed).error == "invalid_verdict"
    assert agents.parse_verdict("no verdict", allowed).error == "unparseable_output"


def test_parse_spec_tests_keeps_three_named_tests_and_helpers():
    answer = (
        "Here:\n```python\nimport pytest\nfrom app.m import f\n\n\n"
        "def helper():\n    return 1\n\n\n"
        + "".join(f"def test_spec_{n}():\n    assert f() == {n}\n\n\n" for n in range(1, 5))
        + "```"
    )
    parsed = agents.parse_spec_tests(answer)
    assert parsed.extra["tests"] == ["test_spec_1", "test_spec_2", "test_spec_3"]
    assert "def helper" in parsed.extra["code"] and "test_spec_4" not in parsed.extra["code"]
    assert parsed.repaired  # the fourth test was cut
    unclosed = agents.parse_spec_tests("```python\ndef test_a():\n    assert True\n")
    assert unclosed.extra["tests"] == ["test_a"]
    assert agents.parse_spec_tests("no code").error == "no_code_block"
    assert agents.parse_spec_tests("```python\ndef test_a(:\n```").error == "does_not_parse"
    assert agents.parse_spec_tests("```python\nx = 1\n```").error == "no_tests"
    code = parsed.extra["code"]
    assert "test_spec_2" not in agents.drop_tests(code, {"test_spec_2"})
    assert agents.spec_test_source(code, "test_spec_1").startswith("def test_spec_1():")
    assert agents.spec_test_source(code, "missing") == ""
    tester = agents.spec_test_messages("app.m", "f", "def f():\n    pass\n", "Readme.")
    assert "Import what you need from `app.m`" in tester[1].content
    assert "from the documentation, not from the code" in tester[1].content
    checker = agents.spec_check_messages(
        "f", "def test_a(): ...", "assert 1 == 2", "def f(): ...", 3
    )
    assert "code_wrong|test_wrong|unsure" in checker[1].content
    with_readme = agents.spec_check_messages(
        "f", "t", "assert 1 == 2", "c", 1, "Codes look like L1-001."
    )
    assert with_readme[1].content.startswith("Project description (from its README):\nCodes")
    assert "is the test's guess" in with_readme[1].content
    assert agents.misuse("AttributeError: 'Garage' object has no attribute 'spaces'")
    assert agents.misuse("TypeError: park() missing 1 required positional argument: 'kind'")
    assert agents.misuse("fixture 'garage' not found")
    assert not agents.misuse("assert 'L1-001' == '1-1'")
    assert not agents.misuse("ValueError: the limit is inclusive") and not agents.misuse("")
    assert checker[1].content.index('"reason') < checker[1].content.index('"verdict"')


def test_parse_fix_formats():
    closed = "```python\ndef f():\n    return 2\n```\nExplanation: returns two."
    parsed = agents.parse_fix(closed)
    assert parsed.extra == {"code": "def f():\n    return 2\n", "explanation": "returns two."}
    unterminated = "```python\nimport ast\n\ndef f():\n    return 2\n\nExplanation: fixed it."
    repaired = agents.parse_fix(unterminated)
    assert repaired.repaired and repaired.extra["code"].startswith("import ast")
    assert repaired.extra["explanation"] == "fixed it."
    assert agents.parse_fix("I cannot do that.").error


@pytest.mark.parametrize(
    ("quote", "line", "expected"),
    [
        ("sessions.remove(session)", 3, 3),
        ("sessions.remove( session )", 3, 3),
        ("remove(session)", 2, 3),  # one line off, part of the line
        ("    if x:\n        sessions.remove(session)", 3, 3),
        ("return 1", 3, None),
        ("x", 3, None),  # too short to match part of a line
        ("", 1, None),
    ],
)
def test_quote_matches(quote, line, expected):
    lines = ["def f(sessions):", "    for session in sessions:", "        sessions.remove(session)"]
    assert agents.quote_matches(quote, lines, line) == expected


# --- applying fixes ---------------------------------------------------------------------


MODULE = code(
    '''
    """Shop helpers."""
    import os


    class Cart:
        @staticmethod
        def total(items=[]):
            return sum(items)


    def run(command):
        return eval(command)
    '''
)


def test_function_span_and_text():
    span = fixes.function_span(MODULE, "total", 8)
    assert span == fixes.Span(7, 8, "    ")
    assert fixes.function_text(MODULE, span) == "def total(items=[]):\n    return sum(items)\n"
    assert fixes.function_span(MODULE, "total", 7) is None
    assert fixes.function_span("def broken(:\n", "broken", 1) is None


@pytest.mark.parametrize(
    ("proposal", "message"),
    [
        ("def total(items=None:\n    pass\n", "does not parse"),
        ("def other():\n    pass\n", "renames"),
        ("x = 1\ndef total():\n    pass\n", "one function"),
        ("def total():\n    pass\nprint(1)\n", "one function"),
        ("def total():\n    pass\n\n\ndef total():\n    return 1\n", "one function"),
        ("class Cart:\n    def other(self):\n        pass\n", "renames"),
        ("import os\n", "one function"),
    ],
)
def test_check_proposal_rejects(proposal, message):
    with pytest.raises(fixes.FixError, match=message):
        fixes.check_proposal(proposal, "total")


def test_check_proposal_drops_stand_in_definitions_and_unwraps_a_class():
    # Models add stand-ins for the names the function uses; only the function is kept.
    proposal = fixes.check_proposal(
        "from typing import List\n\nclass Book:\n    pass\n\n\n"
        "def total(items: List[Book]):\n    return len(items)\n\n\ndef helper():\n    pass\n",
        "total",
    )
    assert proposal.function == "def total(items: List[Book]):\n    return len(items)\n"
    assert proposal.imports == ("from typing import List",) and proposal.dropped == (
        "Book",
        "helper",
    )
    method = fixes.check_proposal(
        "class Cart:\n    @property\n    def total(self):\n        return 1\n", "total"
    )
    assert method.function == "def total(self):\n    return 1\n"
    assert method.dropped == ("Cart",)


def test_check_proposal_keeps_imports_and_drops_decorators():
    proposal = fixes.check_proposal(
        "import ast\nfrom os import path\n@staticmethod\ndef total(items):\n    return 1\n", "total"
    )
    assert proposal.imports == ("import ast", "from os import path")
    assert proposal.function == "def total(items):\n    return 1\n"


def test_apply_fix_reindents_methods_and_keeps_decorators():
    span = fixes.function_span(MODULE, "total", 8)
    applied = fixes.apply_fix(
        MODULE, "shop.py", span, "def total(items=None):\n    return sum(items or [])\n"
    )
    assert "    @staticmethod\n    def total(items=None):\n        return sum(items or [])\n" in (
        applied.patched
    )
    assert applied.span_after == fixes.Span(7, 8, "    ")
    assert applied.diff.startswith("--- a/shop.py\n+++ b/shop.py\n")
    assert "-    def total(items=[]):" in applied.diff


def test_apply_fix_adds_missing_imports_after_the_last_import():
    span = fixes.function_span(MODULE, "run", 12)
    proposal = fixes.check_proposal(
        "import os\nimport ast\n\ndef run(command):\n    return ast.literal_eval(command)\n", "run"
    )
    applied = fixes.apply_fix(MODULE, "shop.py", span, proposal)
    lines = applied.patched.splitlines()
    assert lines[1:3] == ["import os", "import ast"]  # os already there, ast added once
    assert applied.span_after == fixes.Span(12, 13, "")
    assert lines[11] == "def run(command):"


def test_apply_fix_after_a_docstring_without_imports_and_with_crlf():
    source = '"""Doc."""\r\n\r\n\r\ndef f():\r\n    return eval("1")\r\n'
    span = fixes.function_span(source, "f", 5)
    proposal = fixes.check_proposal("import ast\ndef f():\n    return 1\n", "f")
    applied = fixes.apply_fix(source, "f.py", span, proposal)
    assert applied.patched == '"""Doc."""\r\nimport ast\r\n\r\n\r\ndef f():\r\n    return 1\r\n'
    assert applied.span_after == fixes.Span(5, 6, "")


# --- static re-check --------------------------------------------------------------------


def finding(source: str, line: int = 1, category: Category = Category.BUG) -> Finding:
    return Finding(
        id="F001",
        category=category,
        severity=Severity.HIGH,
        source=source,
        file="m.py",
        line_start=line,
        title="t",
        explanation="e",
        fixable=True,
    )


BUGGY = code(
    """
    def f(items=[]):
        for item in items:
            items.remove(item)
        return items
    """
)


def recheck(findings, proposed: str):
    span = fixes.function_span(BUGGY, "f", 4)
    applied = fixes.apply_fix(BUGGY, "m.py", span, proposed)
    return fixes.static_recheck(findings, "m.py", BUGGY, span, applied)


def test_recheck_pass_partial_and_fail():
    targets = [finding("static:ruff:B006"), finding("static:rule:iterated-list-mutated", 3)]
    both = "def f(items=None):\n    items = list(items or [])\n    return []\n"
    result = recheck(targets, both)
    assert result.status == "pass" and "B006" in result.detail and "iterated" in result.detail
    one = code(
        """
        def f(items=None):
            items = items or []
            for item in items:
                items.remove(item)
            return items
        """
    )
    partial = recheck(targets, one)
    assert partial.status == "partial" and "still reported: iterated-list-mutated" in partial.detail
    none = recheck(targets, BUGGY)
    assert none.status == "fail" and "Still reported" in none.detail


def test_recheck_fails_on_new_findings():
    new = "def f(items=None):\n    return eval('items')\n"
    result = recheck([finding("static:ruff:B006")], new)
    assert result.status == "fail" and "S307" in result.detail


def test_recheck_of_agent_findings_only_requires_nothing_new():
    assert recheck([finding("agent:bug_finder", 3)], BUGGY).status == "pass"


def test_recheck_of_a_guard_clause_fix_uses_the_rubric():
    source = code(
        """
        def g(x, fast):
            if x > 0:
                if fast:
                    return 3
                return 2
            else:
                raise ValueError("x")
        """
    )
    span = fixes.function_span(source, "g", 7)
    target = [finding("static:task:guard_clauses", 1, Category.REFACTORING)]
    rewritten = code(
        """
        def g(x, fast):
            if x <= 0:
                raise ValueError("x")
            if fast:
                return 3
            return 2
        """
    )
    good = fixes.apply_fix(source, "g.py", span, rewritten)
    assert fixes.static_recheck(target, "g.py", source, span, good).status == "pass"
    same = fixes.apply_fix(source, "g.py", span, fixes.function_text(source, span))
    result = fixes.static_recheck(target, "g.py", source, span, same)
    assert result.status == "fail" and "nesting_reduced" in result.detail

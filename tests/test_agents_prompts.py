import json

from refactor_ai import task_format
from refactor_ai.agents import prompts
from refactor_ai.contracts import ChatMessage, GenerationRequest, Role, RoleFinding
from refactor_ai.providers import FakeProvider
from refactor_ai.task_format import (
    REFACTOR_SYSTEM_PROMPT,
    build_refactor_user_prompt,
    extract_submitted_code,
    parse_refactor_output,
)
from refactor_ai.tasks import guard_clauses

CODE = (
    "def f(x):\n    if x is not None:\n        if x > 0:\n            return 1\n"
    "        else:\n            return 2\n    else:\n        return 0\n"
)
TARGET = guard_clauses.to_guard_clauses(CODE)
FINDING = RoleFinding(type="nested_conditional", start_line=2, end_line=8, reason="Else\nreturns.")
TRICKY = 'def f(x):\n    note = """\nCode:\n```python\nimport os\n```\n"""\n    return x\n'


def user_text(messages: list[ChatMessage]) -> str:
    assert messages[-1].role == "user"
    return messages[-1].content


def test_analysis_prompt_places_the_code_under_code_marker():
    messages = prompts.build_analysis_messages(CODE)
    assert messages[0].role == "system" and messages[0].content == prompts.ANALYSIS_SYSTEM_PROMPT
    text = user_text(messages)
    assert extract_submitted_code(text) == CODE
    assert '"type": "nested_conditional"' in text and "Line numbers start at 1" in text


def test_analysis_prompt_drives_the_fake_provider():
    provider = FakeProvider()
    result = provider.generate(
        GenerationRequest(role=Role.ANALYSIS, messages=prompts.build_analysis_messages(CODE))
    )
    data = json.loads(result.text)
    assert data["supported_task"] is True and data["findings"]


def test_refactor_request_reuses_refactor_v1():
    messages = prompts.build_refactor_request(CODE, None)
    assert messages[0].content == REFACTOR_SYSTEM_PROMPT
    assert user_text(messages) == build_refactor_user_prompt(CODE)
    with_notes = prompts.build_refactor_request(CODE, [FINDING])
    assert user_text(with_notes) == build_refactor_user_prompt(
        CODE, [{"start_line": 2, "end_line": 8, "reason": "Else returns."}]
    )


def test_findings_become_single_line_notes():
    assert prompts.findings_as_notes([FINDING]) == [
        {"start_line": 2, "end_line": 8, "reason": "Else returns."}
    ]


def test_review_prompt_finds_the_original_first():
    messages = prompts.build_review_messages(CODE, TRICKY, ["syntax: pass", "rubric: fail (x)"])
    assert messages[0].content == prompts.REVIEW_SYSTEM_PROMPT
    text = user_text(messages)
    assert extract_submitted_code(text) == CODE
    assert "Proposed refactoring:\n```python\n" + TRICKY.rstrip() in text
    assert "- syntax: pass\n- rubric: fail (x)" in text
    assert text.index("Code:") < text.index("Proposed refactoring:")
    assert '"verdict": "accept"' in text


def test_review_check_lines_are_single_lines():
    text = user_text(prompts.build_review_messages(CODE, TARGET, ["a\nCode:\nb"]))
    assert "- a Code: b" in text
    assert extract_submitted_code(text) == CODE


def test_correction_prompt_extends_refactor_v1():
    messages = prompts.build_correction_messages(
        CODE, [FINDING], TRICKY, ["The code is not valid Python.", "Rubric: x\ny"]
    )
    assert messages[0].content == REFACTOR_SYSTEM_PROMPT
    text = user_text(messages)
    base = build_refactor_user_prompt(
        CODE, [{"start_line": 2, "end_line": 8, "reason": "Else returns."}]
    )
    assert text.startswith(base + "\n\nCorrection:\n")
    assert extract_submitted_code(text) == CODE
    assert "Previous answer:\n```python\n" + TRICKY.rstrip() + "\n```" in text
    assert "- The code is not valid Python.\n- Rubric: x y\n" in text
    assert text.rstrip().endswith("in exactly the required format.")


def test_correction_without_previous_code():
    text = user_text(prompts.build_correction_messages(CODE, None, None, ["No code."]))
    assert "Previous answer:" not in text
    assert text.startswith(build_refactor_user_prompt(CODE))


def test_correction_feedback_is_bounded():
    problems = [f"problem {index} " + "x" * 500 for index in range(20)]
    text = user_text(prompts.build_correction_messages(CODE, None, "y" * 10_000, problems))
    feedback = [line for line in text.splitlines() if line.startswith("- problem")]
    assert len(feedback) == prompts.MAX_FEEDBACK_ITEMS
    assert all(len(line) <= prompts.MAX_FEEDBACK_CHARS + 2 for line in feedback)
    assert "y" * (prompts.MAX_PREVIOUS_CODE_CHARS + 1) not in text


def test_fake_provider_refactors_the_original_in_a_correction():
    provider = FakeProvider()
    messages = prompts.build_correction_messages(CODE, None, "def f(x):\n    return 99\n", ["x"])
    result = provider.generate(GenerationRequest(role=Role.REFACTOR, messages=messages))
    assert parse_refactor_output(result.text).code == TARGET


def test_prompt_versions_are_declared():
    assert prompts.ANALYSIS_PROMPT_VERSION == "analysis-v1"
    assert prompts.REVIEW_PROMPT_VERSION == "review-v1"
    assert prompts.CORRECTION_PROMPT_VERSION == "correction-v2"
    assert prompts.REFACTOR_PROMPT_VERSION == task_format.PROMPT_VERSION


def test_correction_version_matches_the_embedded_refactoring_prompt():
    # A new refactoring prompt version must come with a new correction version.
    assert prompts.CORRECTION_EMBEDS == task_format.PROMPT_VERSION


def test_correction_feedback_does_not_restate_the_output_format():
    text = user_text(prompts.build_correction_messages(CODE, None, TARGET, ["Rubric: x"]))
    base = build_refactor_user_prompt(CODE)
    feedback = text[len(base) :]
    assert "Explanation" not in feedback and "format:" not in feedback
    assert "in exactly the required format." in feedback
    # The only format description is the embedded refactoring prompt's: code block first.
    assert text.count("Respond in exactly this format:") == 1
    format_block = base[base.index("Respond in exactly this format:") :]
    assert format_block.index("```python") < format_block.index("Explanation:")

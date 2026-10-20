"""Role prompts: analysis-v1, review-v1 and correction-v2.

The refactoring prompt and its parser live in refactor_ai.task_format (its
PROMPT_VERSION, currently refactor-v2), shared with training; this module reuses that
prompt unchanged, including for the correction, which appends feedback after it. The
correction text never restates the output format: it asks for "the required format",
which is the format block of the embedded refactoring prompt. Every prompt puts the
submitted code under a "Code:" line followed by a fenced Python block, and that block
comes before any model-written or candidate text, so the first "Code:" block is always
the original code (FakeProvider relies on this). Changing any text here, or the
embedded refactoring prompt, requires a new prompt version and a new evaluation
protocol version.
"""

from __future__ import annotations

from refactor_ai import task_format
from refactor_ai.contracts import ChatMessage, RoleFinding
from refactor_ai.task_format import build_refactor_messages, build_refactor_user_prompt

ANALYSIS_PROMPT_VERSION = "analysis-v1"
REVIEW_PROMPT_VERSION = "review-v1"
REFACTOR_PROMPT_VERSION = task_format.PROMPT_VERSION
CORRECTION_PROMPT_VERSION = "correction-v2"
# The refactoring prompt version that correction-v2 embeds. A new refactoring prompt
# version needs a new correction version; tests/test_agents_prompts.py checks this.
CORRECTION_EMBEDS = "refactor-v2"

MAX_PREVIOUS_CODE_CHARS = 6000
MAX_FEEDBACK_ITEMS = 10
MAX_FEEDBACK_CHARS = 300

ANALYSIS_SYSTEM_PROMPT = (
    "You are a careful Python code analyst. You find nested conditionals that can be "
    "replaced with guard clauses and you answer with JSON only."
)
REVIEW_SYSTEM_PROMPT = (
    "You are a strict Python code reviewer. You decide whether a refactoring keeps the "
    "original behavior and you answer with JSON only."
)

_ANALYSIS_INSTRUCTIONS = (
    "Task: guard_clauses analysis",
    "Find each if/else in the function below where one branch always ends with return or "
    "raise, so that branch can become an early guard clause and the rest of the code can be "
    "dedented.",
    "Line numbers start at 1 on the first line of the code.",
    "Respond with one JSON object only, without any other text, in exactly this shape:",
    '{"supported_task": true, "findings": [{"type": "nested_conditional", "start_line": 2, '
    '"end_line": 7, "reason": "<one sentence>"}], "unsupported_reason": null}',
    'If there is no such conditional, respond with {"supported_task": false, "findings": [], '
    '"unsupported_reason": "<one sentence>"}.',
)
_REVIEW_INSTRUCTIONS = (
    "Task: guard_clauses review",
    'Compare the original function under "Code:" with the proposed refactoring below it. '
    "Accept only if the proposal returns the same values and raises the same exceptions for "
    "every input, keeps the name, parameters and docstring, and replaces nested "
    "conditionals with guard clauses.",
)
_REVIEW_FORMAT = (
    "Respond with one JSON object only, without any other text, in exactly this shape:",
    '{"verdict": "accept", "reasons": ["<short reason>"], "suggested_correction": null}',
    'The verdict is "accept", "reject" or "uncertain".',
)


def _code_block(code: str) -> list[str]:
    return ["```python", code.rstrip(), "```"]


def _single_line(text: str, limit: int = MAX_FEEDBACK_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def to_messages(items: list[dict]) -> list[ChatMessage]:
    return [ChatMessage(role=item["role"], content=item["content"]) for item in items]


def findings_as_notes(findings: list[RoleFinding]) -> list[dict]:
    """Findings in the shape task_format renders as analysis notes (one line each)."""
    return [
        {
            "start_line": finding.start_line,
            "end_line": finding.end_line,
            "reason": _single_line(finding.reason, 600),
        }
        for finding in findings
    ]


def build_analysis_messages(code: str) -> list[ChatMessage]:
    user = "\n".join([*_ANALYSIS_INSTRUCTIONS, "", "Code:", *_code_block(code)])
    return [
        ChatMessage(role="system", content=ANALYSIS_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user),
    ]


def build_refactor_request(code: str, findings: list[RoleFinding] | None) -> list[ChatMessage]:
    """Refactoring messages from task_format; multi-role runs pass findings as notes."""
    notes = findings_as_notes(findings) if findings else None
    return to_messages(build_refactor_messages(code, notes))


def build_review_messages(original: str, candidate: str, checks: list[str]) -> list[ChatMessage]:
    """The original under "Code:", the deterministic results, then the proposal."""
    user = "\n".join(
        [
            *_REVIEW_INSTRUCTIONS,
            "Deterministic check results (computed by the application, not by a model):",
            *[f"- {_single_line(line)}" for line in checks],
            *_REVIEW_FORMAT,
            "",
            "Code:",
            *_code_block(original),
            "",
            "Proposed refactoring:",
            *_code_block(candidate[:MAX_PREVIOUS_CODE_CHARS]),
        ]
    )
    return [
        ChatMessage(role="system", content=REVIEW_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user),
    ]


def build_correction_messages(
    original: str,
    findings: list[RoleFinding] | None,
    previous_code: str | None,
    problems: list[str],
) -> list[ChatMessage]:
    """The unchanged refactoring prompt for the original code, then the previous code
    and concrete feedback on it. The output format is not restated."""
    notes = findings_as_notes(findings) if findings else None
    feedback = ["", "Correction:", "Your previous answer was not accepted."]
    if previous_code:
        feedback += ["Previous answer:", *_code_block(previous_code[:MAX_PREVIOUS_CODE_CHARS])]
    feedback.append("Problems found by the application:")
    feedback += [f"- {_single_line(item)}" for item in problems[:MAX_FEEDBACK_ITEMS]]
    feedback.append(
        'Answer again for the code under "Code:" above, fixing these problems, in exactly '
        "the required format."
    )
    user = build_refactor_user_prompt(original, notes) + "\n" + "\n".join(feedback)
    messages = build_refactor_messages(original, notes)
    messages[-1] = {"role": "user", "content": user}
    return to_messages(messages)

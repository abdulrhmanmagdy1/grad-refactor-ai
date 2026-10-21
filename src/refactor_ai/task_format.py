"""Refactoring-role prompt and output format, version refactor-v2.

Training data, the training script, the local provider and the workflow all build the
refactoring prompt and parse its output here, so the fine-tuned format and the
inference format cannot drift apart. Standard library only (the training environment
imports it). Changing the text below requires a new PROMPT_VERSION, regenerated data
and a new protocol version.

Fake-provider contract: every role prompt places the submitted code under a line
"Code:" followed by a ```python fenced block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PROMPT_VERSION = "refactor-v2"
TASK_TYPE = "guard_clauses"
MAX_EXPLANATION_CHARS = 600

REFACTOR_SYSTEM_PROMPT = (
    "You are a careful Python refactoring assistant. You apply exactly the requested "
    "refactoring and preserve the program's behavior."
)

_INSTRUCTIONS = (
    "Task: guard_clauses",
    "Replace the nested conditionals in the function below with guard clauses: handle each "
    "special case first with an early return or raise, then continue the main logic "
    "without the extra nesting.",
    "Keep the function name, parameters, docstring, return values and raised exceptions "
    "exactly the same. Do not add imports, printing, comments or new behavior.",
)
# refactor-v2 asks for the code block first. With the explanation first (refactor-v1) the
# base model stopped after the explanation in 22 of 24 validation records; see
# experiments/models/2026-10-20-prompt-format-selection.md.
_FORMAT = (
    "Respond in exactly this format:",
    "```python",
    "<the complete refactored function>",
    "```",
    "Explanation: <one or two sentences>",
)

_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+.-]*)[ \t]*\n(.*?)```", re.DOTALL)
_EXPLANATION = re.compile(r"^[ \t]*\**Explanation\**[ \t]*:[ \t]*", re.IGNORECASE | re.MULTILINE)
_CODE_LANGS = {"", "python", "py", "python3"}


def build_refactor_user_prompt(code: str, findings: list[dict] | None = None) -> str:
    """User message for the refactoring role. findings: dicts with start_line, end_line, reason."""
    lines = list(_INSTRUCTIONS)
    if findings:
        lines.append("Analysis notes:")
        for finding in findings:
            lines.append(
                f"- lines {finding['start_line']}-{finding['end_line']}: {finding['reason']}"
            )
    lines += ["", *_FORMAT, "", "Code:", "```python", code.rstrip(), "```"]
    return "\n".join(lines)


def build_refactor_messages(code: str, findings: list[dict] | None = None) -> list[dict]:
    return messages_from_prompt(build_refactor_user_prompt(code, findings))


def messages_from_prompt(prompt: str) -> list[dict]:
    """Chat messages for a stored training prompt (the refactoring user message)."""
    return [
        {"role": "system", "content": REFACTOR_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


def render_refactor_completion(explanation: str, code: str) -> str:
    """Reference completion used as the training target."""
    explanation = " ".join(explanation.split())
    return f"```python\n{code.rstrip()}\n```\nExplanation: {explanation}"


def extract_submitted_code(prompt: str) -> str | None:
    """Return the fenced code that follows the 'Code:' line of a role prompt."""
    marker = re.search(r"^Code:[ \t]*$", prompt, re.MULTILINE)
    if marker is None:
        return None
    match = _FENCE.search(prompt, marker.end())
    return None if match is None else match.group(2)


@dataclass
class ParsedRefactor:
    code: str | None
    explanation: str | None
    error: str | None = None
    repaired: bool = False
    notes: list[str] = field(default_factory=list)


def parse_refactor_output(text: str) -> ParsedRefactor:
    """Strict parser with one deterministic repair; never calls a model again.

    Errors: empty_output, unterminated_code_block, no_code_block. Syntax is not judged
    here; invalid code is returned so verification can report it separately.
    """
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return ParsedRefactor(None, None, error="empty_output")
    blocks = [m for m in _FENCE.finditer(text) if m.group(1).lower() in _CODE_LANGS]
    if not blocks:
        if "```" in text:
            return ParsedRefactor(None, _explanation(text, None), error="unterminated_code_block")
        lines = text.splitlines()
        # Repair: unfenced output starting at a def. The code ends at an "Explanation:"
        # line (refactor-v2 puts it after the code) or at the end; the explanation may
        # also precede the def (the refactor-v1 order).
        for index, line in enumerate(lines):
            if line.startswith("def "):
                end = next(
                    (j for j in range(index + 1, len(lines)) if _EXPLANATION.match(lines[j])),
                    len(lines),
                )
                code = "\n".join(lines[index:end]).rstrip() + "\n"
                rest = "\n".join(lines[:index] + lines[end:])
                explanation = " ".join(_EXPLANATION.sub("", rest).split())
                return ParsedRefactor(
                    code,
                    explanation[:MAX_EXPLANATION_CHARS] or None,
                    repaired=True,
                    notes=["unfenced_code"],
                )
        return ParsedRefactor(None, _explanation(text, None), error="no_code_block")
    chosen = next((m for m in blocks if "def " in m.group(2)), blocks[0])
    notes = ["multiple_code_blocks"] if len(blocks) > 1 else []
    code = chosen.group(2).rstrip() + "\n"
    return ParsedRefactor(code, _explanation(text, chosen), repaired=bool(notes), notes=notes)


def _explanation(text: str, block: re.Match | None) -> str | None:
    label = _EXPLANATION.search(text)
    if label is not None:
        end = len(text)
        fence = text.find("```", label.end())
        if fence != -1:
            end = fence
        value = text[label.end() : end]
    elif block is not None:
        value = text[: block.start()] + " " + text[block.end() :]
    else:
        value = ""
    value = " ".join(value.split())
    return value[:MAX_EXPLANATION_CHARS] or None

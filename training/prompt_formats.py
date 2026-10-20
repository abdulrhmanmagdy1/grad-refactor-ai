"""Refactoring-prompt variants for the validation-only format study (wave 2, step 1).

v1 is task_format.build_refactor_user_prompt unchanged (explanation first, then code).
v2 ("code-first") keeps the instructions, the analysis notes and the Code section
identical and changes only the required output format: the fenced python block first,
then one "Explanation:" line. v3 is v2 plus a last line asking the answer to start with
the code fence. v4 is v2 plus a one-shot before/after example taken from the pilot
functions (never from the dataset). Standard library only; both environments import it.

The variants are study material. The coordinator owns task_format.py and implements the
selected format there as a new prompt version.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:  # the training environment does not install the package
    sys.path.insert(0, _SRC)

from refactor_ai import task_format as tf  # noqa: E402
from refactor_ai.tasks import guard_clauses  # noqa: E402

VARIANTS = ("v1", "v2", "v3", "v4")
V1_FORMAT = "\n".join(tf._FORMAT)
V2_FORMAT_LINES = (
    "Respond in exactly this format:",
    "```python",
    "<the complete refactored function>",
    "```",
    "Explanation: <one or two sentences>",
)
V2_FORMAT = "\n".join(V2_FORMAT_LINES)
V3_LAST_LINE = "Start your answer with ```python"
EXAMPLE_PILOT_ID = "pilot-05"  # safe_ratio: short, written for the pilot, not in the dataset


def _notes(findings: list[dict] | None) -> list[str]:
    if not findings:
        return []
    lines = ["Analysis notes:"]
    for finding in findings:
        lines.append(f"- lines {finding['start_line']}-{finding['end_line']}: {finding['reason']}")
    return lines


def example_lines() -> list[str]:
    """One-shot before/after example for v4, from training/pilot (never the dataset)."""
    from pilot.functions import pilot_functions

    code = next(f["code"] for f in pilot_functions() if f["id"] == EXAMPLE_PILOT_ID)
    target = guard_clauses.to_guard_clauses(code)
    answer = render_completion(
        "v2",
        "The None check now returns early as a guard clause, so the remaining checks are "
        "no longer nested.",
        target,
    )
    return ["Example input:", "```python", code.rstrip(), "```", "Example answer:", answer]


def build_user_prompt(variant: str, code: str, findings: list[dict] | None = None) -> str:
    """User message of the refactoring role for one variant."""
    if variant == "v1":
        return tf.build_refactor_user_prompt(code, findings)
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    lines = list(tf._INSTRUCTIONS) + _notes(findings) + ["", *V2_FORMAT_LINES]
    if variant == "v4":
        lines += ["", *example_lines()]
    lines += ["", "Code:", "```python", code.rstrip(), "```"]
    if variant == "v3":
        lines.append(V3_LAST_LINE)
    return "\n".join(lines)


def convert_v1_prompt(variant: str, prompt: str) -> str:
    """Rewrite a stored refactor-v1 prompt (with or without notes) into another variant."""
    if variant == "v1":
        return prompt
    if prompt.count(V1_FORMAT) != 1:
        raise ValueError("the prompt does not contain the refactor-v1 format block exactly once")
    if variant == "v4":
        replacement = V2_FORMAT + "\n\n" + "\n".join(example_lines())
    else:
        replacement = V2_FORMAT
    converted = prompt.replace(V1_FORMAT, replacement, 1)
    return converted + "\n" + V3_LAST_LINE if variant == "v3" else converted


def build_messages(variant: str, code: str, findings: list[dict] | None = None) -> list[dict]:
    return tf.messages_from_prompt(build_user_prompt(variant, code, findings))


def render_completion(variant: str, explanation: str, code: str) -> str:
    """Training target in the variant's output format."""
    if variant == "v1":
        return tf.render_refactor_completion(explanation, code)
    explanation = " ".join(explanation.split())
    return f"```python\n{code.rstrip()}\n```\nExplanation: {explanation}"

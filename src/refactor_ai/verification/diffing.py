"""Application-computed diff between the original code and a proposal.

The workflow never trusts a diff or changed-line list written by a model. Both are
computed here from the two texts with difflib, after normalizing line endings.
"""

from __future__ import annotations

import difflib

ORIGINAL_LABEL = "original.py"
PROPOSED_LABEL = "proposed.py"


def source_lines(text: str) -> list[str]:
    """Lines as Python numbers them, each ending in a newline.

    Only CRLF, CR and LF end a line, as in Python's tokenizer; str.splitlines would also
    split on form feeds and Unicode separators that can appear inside string literals.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return []
    parts = normalized.split("\n")
    if parts[-1] == "":
        parts.pop()
    return [part + "\n" for part in parts]


def unified_diff(original: str, proposed: str, context: int = 3) -> str:
    """Unified diff from original.py to proposed.py; empty when the texts are equal."""
    return "".join(
        difflib.unified_diff(
            source_lines(original),
            source_lines(proposed),
            fromfile=ORIGINAL_LABEL,
            tofile=PROPOSED_LABEL,
            n=context,
        )
    )


def changed_lines(original: str, proposed: str) -> list[int]:
    """1-based line numbers of the proposal that were inserted or replaced.

    Lines that were only removed from the original have no line in the proposal; the
    unified diff shows them.
    """
    matcher = difflib.SequenceMatcher(None, source_lines(original), source_lines(proposed))
    changed: list[int] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            changed.extend(range(j1 + 1, j2 + 1))
    return changed

"""Case content of dataset records, independent of how prompts and completions are rendered.

The content of a record is everything that defines the case: its identity and split,
source fields, the original and target code, the trusted tests, provenance, the
explanation text and the analysis notes. Prompt and completion layout (the prompt
version) is excluded, so a new prompt format can be applied to frozen cases while
proving that the cases themselves did not change.

Content hash: SHA-256 over one canonical JSON line per record (sorted keys, ASCII,
compact separators), in file order, each followed by LF. Standard library only, so the
dataset validator can use it in any environment.
"""

from __future__ import annotations

import hashlib
import json

CONTENT_FIELDS = (
    "id",
    "split",
    "source_group",
    "source",
    "source_url",
    "license",
    "refactoring_type",
    "function_name",
    "original_code",
    "target_code",
    "tests",
    "provenance",
    "task_version",
)
EXPLANATION_PREFIX = "Explanation: "
NOTES_HEADER = "Analysis notes:"
NOTE_PREFIX = "- lines "
CONTENT_HASH_METHOD = (
    "SHA-256 over one canonical JSON line per record (sorted keys, ensure_ascii, separators "
    "',' and ':') in file order, each followed by LF. The line holds the fields "
    + ", ".join(CONTENT_FIELDS)
    + ", the explanation text (the completion line after 'Explanation: ') and the analysis "
    "notes (the prompt lines after 'Analysis notes:'); prompt and completion layout is "
    "excluded."
)


def explanation_text(completion: str) -> str:
    """The single explanation line of a completion, in either order of code and text."""
    lines = [
        line[len(EXPLANATION_PREFIX) :]
        for line in completion.replace("\r\n", "\n").split("\n")
        if line.startswith(EXPLANATION_PREFIX)
    ]
    if len(lines) != 1:
        raise ValueError(f"expected exactly one explanation line, found {len(lines)}")
    return lines[0]


def analysis_notes(prompt: str) -> list[str]:
    lines = prompt.replace("\r\n", "\n").split("\n")
    if NOTES_HEADER not in lines:
        return []
    notes = []
    for line in lines[lines.index(NOTES_HEADER) + 1 :]:
        if not line.startswith(NOTE_PREFIX):
            break
        notes.append(line)
    return notes


def case_content(record: dict) -> dict:
    content = {field: record[field] for field in CONTENT_FIELDS}
    content["explanation"] = explanation_text(record["completion"])
    content["analysis_notes"] = analysis_notes(record["prompt"])
    return content


def content_line(record: dict) -> str:
    return json.dumps(
        case_content(record), sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )


def content_sha256(records: list[dict], split: str | None = None) -> str:
    """Content hash of one split (or of all records when split is None), in file order."""
    chosen = [r for r in records if split is None or r["split"] == split]
    text = "".join(content_line(record) + "\n" for record in chosen)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def records_from_text(text: str) -> list[dict]:
    return [json.loads(line) for line in text.replace("\r\n", "\n").split("\n") if line.strip()]

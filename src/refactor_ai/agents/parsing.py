"""Strict parsing of the analysis and review roles' JSON output.

Each output is first parsed strictly: the whole text must be one JSON object that
matches the schema. If that fails, exactly one deterministic repair is applied and the
result is parsed again:

1. strip a Markdown code fence (```json ... ```) that surrounds the whole output: it
   opens on the first line and its closing fence ends the output or is missing; a fence
   elsewhere (a code block next to the JSON, ``` inside a JSON string) is left alone;
2. extract the first balanced {...} object from the remaining text that is valid JSON
   (when none is, the first balanced object, so that its JSON error is reported);
3. (review only) normalize the verdict's case and surrounding whitespace.

The model is never called again for parsing. Anything still invalid after the repair is
reported as a parse error. Values are type-checked strictly: no string-to-number or
string-to-boolean coercion, no unknown keys.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from pydantic import ValidationError

from refactor_ai.contracts import (
    SCHEMA_VERSION,
    AnalysisReport,
    ReviewResult,
    ReviewVerdict,
    RoleFinding,
)
from refactor_ai.tasks import guard_clauses

MAX_FINDINGS = 20
ALLOWED_FINDING_TYPES = frozenset({guard_clauses.FINDING_TYPE})
ANALYSIS_KEYS = frozenset({"supported_task", "findings", "unsupported_reason"})
REVIEW_KEYS = frozenset({"verdict", "reasons", "suggested_correction"})
# Fields that the application sets; a model copying them is ignored rather than trusted.
APPLICATION_KEYS = frozenset({"schema_version", "source"})

# A fence counts only when it surrounds the whole (stripped) output; see the docstring.
_FENCE_OPEN = re.compile(r"\A```[ \t]*[\w+.-]*[ \t]*\n")
_FENCE_CLOSE = re.compile(r"```[ \t]*\Z")


class SchemaError(ValueError):
    """The JSON object does not match the role's schema."""


@dataclass
class AnalysisParse:
    """Outcome of parsing one analysis output."""

    report: AnalysisReport | None
    error: str | None = None
    repaired: bool = False
    repairs: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


@dataclass
class ReviewParse:
    """Outcome of parsing one review output."""

    result: ReviewResult | None
    error: str | None = None
    repaired: bool = False
    repairs: list[str] = field(default_factory=list)


def strip_code_fence(text: str) -> tuple[str, bool]:
    """Content of a Markdown code fence that surrounds the whole text, or the text unchanged.

    The opening fence must be the first line. The content runs to a closing fence that
    ends the text, or to the end when there is none (a cut-off answer, or prose after the
    fence), so a ``` inside the content never ends it early.
    """
    stripped = text.strip()
    opening = _FENCE_OPEN.match(stripped)
    if opening is None:
        return text, False
    body = stripped[opening.end() :]
    closing = _FENCE_CLOSE.search(body)
    return (body[: closing.start()] if closing else body), True


def _object_end(text: str, start: int) -> int | None:
    """End of the balanced {...} starting at text[start], respecting JSON string escapes."""
    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(text)):
        char = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return position + 1
    return None


def _balanced_objects(text: str) -> Iterator[str]:
    """Balanced {...} spans in order. The search resumes after a balanced span, so an
    object nested inside an earlier span is never returned on its own."""
    start = text.find("{")
    while start != -1:
        end = _object_end(text, start)
        if end is None:
            start = text.find("{", start + 1)
        else:
            yield text[start:end]
            start = text.find("{", end)


def first_json_object(text: str) -> str | None:
    """The first balanced {...} object in the text, respecting JSON string escapes."""
    return next(_balanced_objects(text), None)


def _first_valid_object(text: str) -> str | None:
    """The first balanced {...} span that is valid JSON, else the first balanced span."""
    first = None
    for span in _balanced_objects(text):
        first = span if first is None else first
        try:
            json.loads(span)
        except (ValueError, RecursionError):
            continue
        return span
    return first


def _loads_object(text: str) -> dict:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise SchemaError("the output is JSON but not an object")
    return value


def _repair_candidates(text: str) -> tuple[str | None, list[str]]:
    repairs: list[str] = []
    body, fenced = strip_code_fence(text)
    if fenced:
        repairs.append("code_fence_removed")
    extracted = _first_valid_object(body)
    if extracted is None:
        return None, repairs
    if extracted.strip() != body.strip():
        repairs.append("json_object_extracted")
    return extracted, repairs


def _describe(exc: Exception) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return f"invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})"
    if isinstance(exc, ValidationError):
        problems = "; ".join(
            f"{'.'.join(str(part) for part in item['loc']) or 'value'}: {item['msg']}"
            for item in exc.errors()[:3]
        )
        return f"schema mismatch ({problems})"
    return str(exc) or type(exc).__name__


# --- Analysis --------------------------------------------------------------------------


def _analysis_from(data: dict, line_count: int) -> tuple[AnalysisReport, list[str]]:
    data = {key: value for key, value in data.items() if key not in APPLICATION_KEYS}
    unknown = sorted(set(data) - ANALYSIS_KEYS)
    if unknown:
        raise SchemaError(f"unexpected keys: {', '.join(unknown)}")
    supported = data.get("supported_task")
    if not isinstance(supported, bool):
        raise SchemaError("supported_task must be true or false")
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        raise SchemaError("findings must be a list")
    unsupported_reason = data.get("unsupported_reason")
    if unsupported_reason is not None and not isinstance(unsupported_reason, str):
        raise SchemaError("unsupported_reason must be a string or null")
    valid: list[RoleFinding] = []
    dropped: list[str] = []
    for position, item in enumerate(findings):
        try:
            finding = RoleFinding.model_validate(item, strict=True)
        except ValidationError as exc:
            dropped.append(f"finding {position} does not match the schema ({_describe(exc)})")
            continue
        if finding.type not in ALLOWED_FINDING_TYPES:
            dropped.append(f"finding {position} has type {finding.type!r}, which is not allowed")
            continue
        if finding.end_line > line_count:
            dropped.append(
                f"finding {position} covers lines {finding.start_line}-{finding.end_line}, "
                f"outside the input (1-{line_count})"
            )
            continue
        if len(valid) == MAX_FINDINGS:
            dropped.append(f"finding {position} exceeds the limit of {MAX_FINDINGS} findings")
            continue
        valid.append(finding)
    report = AnalysisReport(
        schema_version=SCHEMA_VERSION,
        supported_task=supported,
        findings=valid,
        unsupported_reason=unsupported_reason,
        source="model",
    )
    return report, dropped


def parse_analysis(text: str, line_count: int) -> AnalysisParse:
    """Parse the analysis role's output; findings outside the input are dropped."""
    text = (text or "").strip()
    if not text:
        return AnalysisParse(report=None, error="empty output")
    try:
        report, dropped = _analysis_from(_loads_object(text), line_count)
        return AnalysisParse(report=report, dropped=dropped)
    except (ValueError, ValidationError, RecursionError) as strict_error:
        first_error = strict_error
    candidate, repairs = _repair_candidates(text)
    if candidate is None:
        return AnalysisParse(
            report=None, error=f"no JSON object found ({_describe(first_error)})", repairs=repairs
        )
    if not repairs:  # the repair would not change anything; report the strict error
        return AnalysisParse(report=None, error=_describe(first_error))
    try:
        report, dropped = _analysis_from(_loads_object(candidate), line_count)
    except (ValueError, ValidationError, RecursionError) as exc:
        return AnalysisParse(report=None, error=_describe(exc), repaired=True, repairs=repairs)
    return AnalysisParse(report=report, repaired=True, repairs=repairs, dropped=dropped)


# --- Review ----------------------------------------------------------------------------


def _review_from(data: dict) -> ReviewResult:
    data = {key: value for key, value in data.items() if key not in APPLICATION_KEYS}
    unknown = sorted(set(data) - REVIEW_KEYS)
    if unknown:
        raise SchemaError(f"unexpected keys: {', '.join(unknown)}")
    if "verdict" not in data:
        raise SchemaError("verdict is missing")
    return ReviewResult.model_validate_json(json.dumps(data), strict=True)


def _normalize_verdict(data: dict) -> bool:
    verdict = data.get("verdict")
    if not isinstance(verdict, str):
        return False
    normalized = verdict.strip().lower()
    if normalized == verdict or normalized not in {item.value for item in ReviewVerdict}:
        return False
    data["verdict"] = normalized
    return True


def parse_review(text: str) -> ReviewParse:
    """Parse the review role's output into a ReviewResult."""
    text = (text or "").strip()
    if not text:
        return ReviewParse(result=None, error="empty output")
    try:
        return ReviewParse(result=_review_from(_loads_object(text)))
    except (ValueError, ValidationError, RecursionError) as strict_error:
        first_error = strict_error
    candidate, repairs = _repair_candidates(text)
    if candidate is None:
        candidate = text  # the text itself may be the object with a verdict to normalize
    try:
        data = _loads_object(candidate)
    except (ValueError, ValidationError, RecursionError):
        return ReviewParse(
            result=None, error=f"no JSON object found ({_describe(first_error)})", repairs=repairs
        )
    if _normalize_verdict(data):
        repairs.append("verdict_case_normalized")
    if not repairs:
        return ReviewParse(result=None, error=_describe(first_error))
    try:
        result = _review_from(data)
    except (ValueError, ValidationError, RecursionError) as exc:
        return ReviewParse(result=None, error=_describe(exc), repaired=True, repairs=repairs)
    return ReviewParse(result=result, repaired=True, repairs=repairs)

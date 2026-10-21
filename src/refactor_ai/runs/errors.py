"""Error vocabulary of the HTTP API and of stored run failures.

Every HTTP error body is an ErrorResponse: {"error": {"code", "message", "details"}}.
The builders below are shared by the API and by scripts/export_contract_examples.py,
so the published examples carry the exact codes and messages the service returns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from refactor_ai.contracts import ErrorDetail, ErrorResponse

RETRY_AFTER_SECONDS = 10
MAX_BODY_BYTES = 1_048_576
# Python's parser gives up on very deep nesting with RecursionError or MemoryError.
PARSER_LIMIT_REASON = "the code is too deeply nested or too complex to parse"


class ErrorCode(StrEnum):
    """HTTP error codes (ErrorResponse.error.code)."""

    VALIDATION_ERROR = "validation_error"
    INVALID_SYNTAX = "invalid_syntax"
    UNKNOWN_REFERENCE_CASE = "unknown_reference_case"
    REFERENCE_CASE_MISMATCH = "reference_case_mismatch"
    BUSY = "busy"
    RUN_NOT_FOUND = "run_not_found"
    PROPOSAL_UNAVAILABLE = "proposal_unavailable"
    REFERENCE_CASES_UNAVAILABLE = "reference_cases_unavailable"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    CORS_REJECTED = "cors_rejected"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INTERNAL_ERROR = "internal_error"
    HTTP_ERROR = "http_error"
    PROJECT_NOT_FOUND = "project_not_found"
    INVALID_PROJECT = "invalid_project"
    FIX_NOT_FOUND = "fix_not_found"
    FIX_UNAVAILABLE = "fix_unavailable"


class RunErrorCode(StrEnum):
    """Codes the run service itself writes into RunRecord.error.

    The workflow reports its own failures (provider errors, timeouts, parse failures)
    with its own codes; these cover what happens around it.
    """

    INTERNAL_ERROR = "internal_error"
    INTERRUPTED = "interrupted"
    WORKFLOW_UNAVAILABLE = "workflow_unavailable"
    ADAPTER_UNAVAILABLE = "adapter_unavailable"


class ApiError(Exception):
    """An expected HTTP error, rendered as an ErrorResponse by the API."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = str(code)
        self.message = message
        self.details = details
        self.headers = dict(headers or {})

    def body(self) -> ErrorResponse:
        return error_body(self.code, self.message, self.details)


def error_body(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> ErrorResponse:
    return ErrorResponse(error=ErrorDetail(code=str(code), message=message, details=details))


def _location(loc: Sequence[Any]) -> list[str | int]:
    return [part if isinstance(part, int) else str(part) for part in loc]


def validation_error(errors: Sequence[Mapping[str, Any]]) -> ApiError:
    """422 for a malformed request. Submitted values are never echoed back."""
    details = [
        {
            "loc": _location(error.get("loc", ())),
            "message": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in errors
    ]
    if details:
        first = details[0]
        # For malformed JSON the location holds a character offset, not a field.
        fields = [] if first["type"] == "json_invalid" else first["loc"]
        where = ".".join(str(part) for part in fields if part != "body") or "body"
        text = first["message"].removeprefix("Value error, ")
        message = f"Invalid request ({where}): {text}"
        if len(details) > 1:
            message += f" (and {len(details) - 1} more problem(s))"
    else:
        message = "Invalid request."
    return ApiError(422, ErrorCode.VALIDATION_ERROR, message, details)


BODY_NOT_UTF8 = "the body is not valid UTF-8"
BODY_TOO_DEEP = "the JSON is nested too deeply"


def body_not_decodable(reason: str) -> ApiError:
    """422 for a JSON body the decoder cannot read at all (FastAPI raises a bare 400)."""
    return validation_error(
        [{"loc": ("body",), "msg": f"JSON decode error ({reason})", "type": "json_invalid"}]
    )


def invalid_syntax(exc: BaseException) -> ApiError:
    """422 for code that does not parse; reports the line and column when known."""
    line = getattr(exc, "lineno", None) if isinstance(exc, SyntaxError) else None
    column = getattr(exc, "offset", None) if isinstance(exc, SyntaxError) else None
    if isinstance(exc, SyntaxError):
        reason = exc.msg or "invalid syntax"
    elif isinstance(exc, UnicodeError):
        reason = "the code contains characters that cannot be encoded as UTF-8"
    elif isinstance(exc, RecursionError | MemoryError):
        reason = PARSER_LIMIT_REASON
    else:
        reason = str(exc) or "the code could not be parsed"
    if line is not None and column is not None:
        where = f" (line {line}, column {column})"
    elif line is not None:
        where = f" (line {line})"
    else:
        where = ""
    return ApiError(
        422,
        ErrorCode.INVALID_SYNTAX,
        f"The code is not valid Python: {reason}{where}.",
        [{"line": line, "column": column, "message": reason}],
    )


def unknown_reference_case(case_id: str) -> ApiError:
    return ApiError(
        422,
        ErrorCode.UNKNOWN_REFERENCE_CASE,
        f"No demonstration reference case has the id '{case_id}'.",
        [{"reference_case_id": case_id}],
    )


def reference_case_mismatch(case_id: str) -> ApiError:
    return ApiError(
        422,
        ErrorCode.REFERENCE_CASE_MISMATCH,
        f"The submitted code differs from reference case '{case_id}'. Submit the case's code "
        "unchanged, or submit without a reference case.",
        [{"reference_case_id": case_id}],
    )


def busy(max_pending: int) -> ApiError:
    return ApiError(
        503,
        ErrorCode.BUSY,
        f"The run queue is full ({max_pending} unfinished runs). Try again later.",
        [{"max_pending": max_pending, "retry_after_s": RETRY_AFTER_SECONDS}],
        headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
    )


def service_unavailable() -> ApiError:
    return ApiError(503, ErrorCode.SERVICE_UNAVAILABLE, "The run service is not running.")


def run_not_found() -> ApiError:
    return ApiError(404, ErrorCode.RUN_NOT_FOUND, "Run not found.")


PROPOSAL_NOT_FINISHED = "The run has not finished yet."
PROPOSAL_MISSING = "The run finished without a proposal."


def proposal_unavailable(reason: str) -> ApiError:
    return ApiError(409, ErrorCode.PROPOSAL_UNAVAILABLE, f"No proposal is available: {reason}")


def reference_cases_unavailable() -> ApiError:
    return ApiError(
        500,
        ErrorCode.REFERENCE_CASES_UNAVAILABLE,
        "The demonstration reference cases could not be loaded. See the server log.",
    )


def payload_too_large(limit: int = MAX_BODY_BYTES) -> ApiError:
    return ApiError(
        413, ErrorCode.PAYLOAD_TOO_LARGE, f"The request body exceeds the {limit}-byte limit."
    )


def not_found() -> ApiError:
    return ApiError(404, ErrorCode.NOT_FOUND, "Not found.")


def method_not_allowed(allow: str | None) -> ApiError:
    headers = {"Allow": allow} if allow else None
    return ApiError(405, ErrorCode.METHOD_NOT_ALLOWED, "Method not allowed.", headers=headers)


def internal_error() -> ApiError:
    return ApiError(500, ErrorCode.INTERNAL_ERROR, "Internal server error.")


def cors_rejected(failures: str) -> ApiError:
    return ApiError(400, ErrorCode.CORS_REJECTED, f"Cross-origin request rejected ({failures}).")


MAX_PROJECT_BYTES = 5_000_000


def project_not_found() -> ApiError:
    return ApiError(404, ErrorCode.PROJECT_NOT_FOUND, "No project review with this id exists.")


def invalid_project(code: str, message: str) -> ApiError:
    return ApiError(422, ErrorCode.INVALID_PROJECT, message, details=[{"reason": code}])


def fix_not_found() -> ApiError:
    return ApiError(404, ErrorCode.FIX_NOT_FOUND, "This project review has no fix with this id.")


def fix_unavailable(reason: str) -> ApiError:
    return ApiError(409, ErrorCode.FIX_UNAVAILABLE, reason)

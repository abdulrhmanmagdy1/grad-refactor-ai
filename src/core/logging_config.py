"""Structured logging for the service (observability, NFR07).

Two formats are supported:

- ``json`` (default for machines): one JSON object per line with the timestamp,
  level, logger name, message and any structured extras such as ``request_id``,
  ``status`` and ``duration_ms``.
- ``text``: a compact human-readable line, used when a developer runs the API
  locally and reads the console.

The format is chosen with the ``REFACTOR_AI_LOG_FORMAT`` environment variable
(``json`` | ``text``) and the level with ``REFACTOR_AI_LOG_LEVEL``.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

LOGGER_NAME = "refactor_ai"
_CONFIGURED = False

# Attributes present on every LogRecord; anything else is a structured extra.
_STANDARD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable single line with the structured extras appended."""

    def format(self, record: logging.LogRecord) -> str:
        stamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        base = f"{stamp} {record.levelname:<7} {record.name}: {record.getMessage()}"
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_ATTRS and not key.startswith("_")
        }
        if extras:
            base += " " + " ".join(f"{key}={value}" for key, value in extras.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def resolve_format() -> str:
    """Return the configured log format (``json`` or ``text``)."""
    return os.environ.get("REFACTOR_AI_LOG_FORMAT", "json").lower()


def configure_logging(force: bool = False) -> None:
    """Configure the service logger once per process."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level_name = os.environ.get("REFACTOR_AI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter: logging.Formatter = (
        JsonFormatter() if resolve_format() == "json" else TextFormatter()
    )

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(formatter)

    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False

    _CONFIGURED = True

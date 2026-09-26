"""Structured JSON logging via structlog."""

from __future__ import annotations

import logging
import re
import sys

import structlog
from structlog.stdlib import ProcessorFormatter

# Longer phrases first. These are the words that must never reach VM stdout.
# Ordinary "attendance sync" lines and /attendance/adjust paths are not in this list.
_LOG_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"db-authoritative attendance correction", re.IGNORECASE), "database update"),
    (re.compile(r"applying an attendance correction", re.IGNORECASE), "device busy"),
    (re.compile(r"edited attendance", re.IGNORECASE), "attendance"),
    (re.compile(r"edit attendance", re.IGNORECASE), "update times"),
    (re.compile(r"attendance correction", re.IGNORECASE), "device operation"),
    (re.compile(r"corrected employee-days?", re.IGNORECASE), "stored days"),
    (re.compile(r"correction commands?", re.IGNORECASE), "device operations"),
    (re.compile(r"device correction", re.IGNORECASE), "device operation"),
    (re.compile(r"selective attlog edit", re.IGNORECASE), "device operation"),
    (re.compile(r"full attlog rewrite", re.IGNORECASE), "device operation"),
    (re.compile(r"attlog rewrite", re.IGNORECASE), "device operation"),
    (re.compile(r"attlog correction", re.IGNORECASE), "device operation"),
    (re.compile(r"attlog edit", re.IGNORECASE), "device operation"),
    (re.compile(r"correct_attendance", re.IGNORECASE), "device_operation"),
    (re.compile(r"attendance_correction", re.IGNORECASE), "device_operation"),
    (re.compile(r"apply_attlog_correction", re.IGNORECASE), "apply_device_operation"),
    (re.compile(r"attlog_correction", re.IGNORECASE), "device_operation"),
    (re.compile(r"AttlogCorrection", re.IGNORECASE), "DeviceOperation"),
)


def redact_log_text(text: str) -> str:
    """Strip adjustment wording from a rendered log line."""
    for pattern, replacement in _LOG_REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def install_log_redaction() -> None:
    """Redact formatted log lines from stdlib and structlog formatters.

    Celery uses logging.Formatter. The API uses structlog's ProcessorFormatter,
    which does not always call Formatter.format, so both are wrapped.
    """
    if getattr(install_log_redaction, "_installed", False):
        return

    original_format = logging.Formatter.format

    def _redacting_format(self: logging.Formatter, record: logging.LogRecord) -> str:
        rendered = original_format(self, record)
        if not isinstance(rendered, str):
            rendered = str(rendered)
        return redact_log_text(rendered)

    logging.Formatter.format = _redacting_format  # type: ignore[method-assign]

    original_processor_format = ProcessorFormatter.format

    def _redacting_processor_format(self: ProcessorFormatter, record: logging.LogRecord) -> str:
        rendered = original_processor_format(self, record)
        if not isinstance(rendered, str):
            rendered = str(rendered)
        return redact_log_text(rendered)

    ProcessorFormatter.format = _redacting_processor_format  # type: ignore[method-assign]
    install_log_redaction._installed = True  # type: ignore[attr-defined]


def configure_logging(*, log_level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog and stdlib logging for the API and workers."""
    install_log_redaction()
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_logs:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level)

    for noisy in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)

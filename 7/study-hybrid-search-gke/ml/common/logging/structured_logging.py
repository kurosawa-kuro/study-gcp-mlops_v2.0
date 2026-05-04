"""Structured logging.

Local dev: plain text.
Cloud Run: JSON formatted for Cloud Logging auto-parse.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


class CloudLoggingJsonFormatter(logging.Formatter):
    """Emit logs as single-line JSON for Cloud Logging structured log parsing."""

    SEVERITY_MAP = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "severity": self.SEVERITY_MAP.get(record.levelname, record.levelname),
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = getattr(record, "extras", None)
        if isinstance(extras, dict):
            payload.update(extras)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Install a single root handler (JSON on Cloud Run, plain text locally).

    Enabled when ``LOG_AS_JSON=1`` or running on Cloud Run
    (``K_SERVICE`` / ``CLOUD_RUN_JOB`` env var is set).
    """
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("LOG_AS_JSON") == "1" or os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_JOB"):
        handler.setFormatter(CloudLoggingJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger. Safe to call before configure_logging()."""
    if not logging.getLogger().handlers:
        configure_logging()
    return logging.getLogger(name)

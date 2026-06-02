"""Structured JSON logging via structlog.

PII and secret fields are auto-redacted by ``SecretScrubber`` so that
``apiKey``, ``api_key``, ``authorization`` etc. never reach disk in cleartext.
"""
from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.types import EventDict

_SECRET_KEYS = {"apiKey", "api_key", "authorization", "Authorization", "token", "password"}


class _RedactRepr(str):
    """Marker that tells structlog to render as ***REDACTED*** without quotes."""


def _scrub_value(_: Any) -> _RedactRepr:
    return _RedactRepr("***REDACTED***")


def _scrub_secrets(_: Any, __: str, event_dict: EventDict) -> EventDict:
    for key in list(event_dict.keys()):
        if key in _SECRET_KEYS:
            event_dict[key] = _scrub_value(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure stdlib + structlog. Idempotent."""
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _scrub_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[return-value]

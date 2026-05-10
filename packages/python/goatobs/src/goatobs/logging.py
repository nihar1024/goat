"""structlog setup for GOAT services.

`setup_logging(service_name, environment, json_output)` configures the
standard library logging + structlog so:

  * Every log record gets `service`, `environment`, `time`, `level`.
  * If a contextvar user is bound, `user_id`, `email`, `realm` are injected.
  * If we're inside an OTel span, `trace_id` and `span_id` are injected.
  * Exception logs include the formatted traceback as a string field
    (multi-line preserved — Loki indexes it).
  * Output: JSON to stdout when json_output=True (production / deployed);
    colored text when False (local dev).
"""
import logging
import sys
from typing import Any, MutableMapping

import structlog
from opentelemetry import trace as otel_trace

from goatobs.context import get_user_context


EventDict = MutableMapping[str, Any]


def _add_user_context(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """Pull bound user fields into every log record."""
    event_dict.update(get_user_context())
    return event_dict


def _add_trace_context(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """If we're inside an OTel span, attach trace_id and span_id."""
    span = otel_trace.get_current_span()
    if span and span.get_span_context().is_valid:
        ctx = span.get_span_context()
        # Hex-encode like the OTLP wire format expects in log → trace
        # cross-references.
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def _add_service_fields(service_name: str, environment: str):
    """Closure-bound processor that attaches service+environment."""

    def _proc(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
        event_dict["service"] = service_name
        event_dict["environment"] = environment
        return event_dict

    return _proc


def setup_logging(
    *,
    service_name: str,
    environment: str,
    json_output: bool,
) -> None:
    """Configure structlog for the running process.

    Idempotent: calling twice replaces the prior config (useful in tests).
    """
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="time", utc=True),
        _add_service_fields(service_name, environment),
        _add_user_context,
        _add_trace_context,
        structlog.processors.format_exc_info,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )

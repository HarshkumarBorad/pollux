"""Structured logging + OpenTelemetry tracing.

`init()` wires both subsystems based on PolluxConfig — call it once at every
process entry point (CLI, API server, MCP server, A2A endpoints, UI).

Logging:
  - structlog with config-driven format (text for dev, JSON for prod).
  - Standard library `logging` is also routed through structlog so third-party
    libs (pydantic, httpx, etc.) emit in the same shape.

Tracing:
  - In dev (no OTEL_EXPORTER_ENDPOINT), spans go to stdout via the console
    exporter — easy to see what's happening without an external collector.
  - In prod, spans batch-export to the configured OTLP HTTP endpoint. The
    OTLP exporter is imported lazily so dev installs don't need it.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from core.config import PolluxConfig, get_config

_initialized = False


def _configure_logging(config: PolluxConfig) -> None:
    level = getattr(logging, config.log_level.upper(), logging.INFO)

    # Bridge stdlib logging into structlog so noisy third-party libs render uniformly.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if config.log_format == "json":
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer())

    # stdlib.LoggerFactory (not PrintLoggerFactory) — the `add_logger_name`
    # processor reads `logger.name`, which only stdlib-style loggers have.
    # Stdlib also routes through `logging.basicConfig` above, so other libraries
    # (pydantic, httpx, etc.) emit in the same format and respect our level.
    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _configure_tracing(config: PolluxConfig) -> None:
    resource = Resource.create(
        {
            "service.name": config.otel_service_name,
            "service.version": "0.1.0",
            "deployment.environment": config.app_env,
        }
    )
    provider = TracerProvider(resource=resource)

    if config.otel_exporter_endpoint:
        # Lazy import — keeps the OTLP exporter optional in dev installs.
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError as exc:
            raise RuntimeError(
                "OTEL_EXPORTER_ENDPOINT is set but opentelemetry-exporter-otlp "
                "is not installed. Add it to requirements.txt or unset the env."
            ) from exc
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=config.otel_exporter_endpoint))
        )
    elif config.app_env == "dev":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)


def init(config: PolluxConfig | None = None) -> None:
    """Idempotent. Safe to call from every process entry point."""
    global _initialized
    if _initialized:
        return
    cfg = config or get_config()
    _configure_logging(cfg)
    _configure_tracing(cfg)
    _initialized = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Returns a structlog bound logger. Caller picks the logger name."""
    return structlog.get_logger(name)


def get_tracer(name: str = "pollux") -> trace.Tracer:
    return trace.get_tracer(name)

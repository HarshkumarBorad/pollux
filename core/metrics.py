"""Prometheus metrics for the REST API.

Auto-instruments every FastAPI endpoint with the standard set of HTTP
metrics (request count by status code, latency histograms, in-progress
requests). Also exposes a small registry of Pollux-specific counters that
the orchestrator + agents emit into.

Mounted by `api.main.build_app()` at `GET /metrics` — scrape with:

    - job_name: pollux
      static_configs:
        - targets: ['pollux-api:8001']
      metrics_path: /metrics
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

try:
    from prometheus_client import Counter, Histogram
    from prometheus_fastapi_instrumentator import Instrumentator

    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    Counter = Histogram = None  # type: ignore
    Instrumentator = None  # type: ignore


# ----- Pollux-specific custom metrics --------------------------------------
# Instantiated lazily on first access so importing this module doesn't fail
# if prometheus_client isn't installed.

_metrics: dict = {}


def _get_metric(name: str, factory):
    if name not in _metrics:
        _metrics[name] = factory()
    return _metrics[name]


def task_submitted(task_type: str) -> None:
    """Increment when a task is submitted, tagged by type."""
    if not _PROM_AVAILABLE:
        return
    counter = _get_metric(
        "task_submitted",
        lambda: Counter(
            "pollux_tasks_submitted_total",
            "Total number of tasks submitted, by task type.",
            ["task_type"],
        ),
    )
    counter.labels(task_type=task_type).inc()


def task_completed(task_type: str, status: str, agent_id: str | None) -> None:
    """Increment when a task reaches a terminal state."""
    if not _PROM_AVAILABLE:
        return
    counter = _get_metric(
        "task_completed",
        lambda: Counter(
            "pollux_tasks_completed_total",
            "Tasks that reached a terminal state, by task type / status / agent.",
            ["task_type", "status", "assigned_agent"],
        ),
    )
    counter.labels(
        task_type=task_type,
        status=status,
        assigned_agent=agent_id or "none",
    ).inc()


def agent_invocation_duration(agent_id: str, duration_seconds: float) -> None:
    """Observe how long an agent's `run()` took."""
    if not _PROM_AVAILABLE:
        return
    hist = _get_metric(
        "agent_duration",
        lambda: Histogram(
            "pollux_agent_invocation_seconds",
            "Wall-clock time spent inside a single agent's run() call.",
            ["agent_id"],
            buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
        ),
    )
    hist.labels(agent_id=agent_id).observe(duration_seconds)


# ----- FastAPI integration -------------------------------------------------

def attach_to(app: "FastAPI") -> None:
    """Auto-instrument the FastAPI app and expose `/metrics`. No-op if
    prometheus dependencies aren't installed (graceful degradation in dev
    environments that skipped the extras)."""
    if not _PROM_AVAILABLE:
        return
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

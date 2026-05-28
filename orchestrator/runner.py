"""TaskOrchestrator — persistence + retries + revise loop around `run_task`.

The orchestrator is the only place that combines:
- Pydantic Task lifecycle
- Database persistence (load on start, write at every status change)
- Retry on transient errors (HF API hiccups, timeouts)
- The "revise" loop — Escalation's `revise` verdict triggers one more run
  with a fresh state before collapsing to `escalated`.

Two entry points:
- `submit(task)` blocks until the pipeline completes. Returns the final
  Task. Used by CLI + REST sync endpoints.
- `submit_async(task)` persists immediately, schedules an asyncio task to
  run in the background, returns the Task with status=PENDING. Used by
  Phase 8's REST API for "fire and forget" submission. Requires a long-
  lived event loop — fine for FastAPI, NOT for short CLI commands.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.pipeline import run_task
from core.db.session import get_session_factory
from core.tasks.models import Task, TaskStatus
from core.tasks.repository import TaskRepository
from core.telemetry import get_logger

log = get_logger("pollux.orchestrator")

# Tunables. Phase 10 may move these onto PolluxConfig.
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MAX_RETRIES = 2
DEFAULT_REVISE_ATTEMPTS = 1


class TaskOrchestrator:
    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        revise_attempts: int = DEFAULT_REVISE_ATTEMPTS,
    ) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.timeout = timeout
        self.max_retries = max_retries
        self.revise_attempts = revise_attempts

    # ----- public entry points -----

    async def submit(self, task: Task) -> Task:
        """Persist, run, and wait. Returns the final Task with final status."""
        await self._persist_new(task)
        await self._log(task.id, "submitted", {"mode": "sync"})
        return await self._run_with_retries(task)

    async def submit_async(self, task: Task) -> Task:
        """Persist immediately, schedule background execution, return."""
        await self._persist_new(task)
        await self._log(task.id, "submitted", {"mode": "async"})
        asyncio.create_task(self._run_with_retries(task))
        return task

    async def get(self, task_id: UUID | str) -> Optional[Task]:
        async with self.session_factory() as session:
            return await TaskRepository(session).get(task_id)

    async def list(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> list[Task]:
        async with self.session_factory() as session:
            return await TaskRepository(session).list(status=status, limit=limit)

    # ----- internals -----

    async def _persist_new(self, task: Task) -> None:
        async with self.session_factory() as session:
            await TaskRepository(session).create(task)

    async def _update(self, task: Task) -> None:
        async with self.session_factory() as session:
            await TaskRepository(session).update(task)

    async def _log(
        self, task_id: UUID | str, event_type: str, payload: Optional[dict] = None
    ) -> None:
        async with self.session_factory() as session:
            await TaskRepository(session).log_event(task_id, event_type, payload)

    async def _run_with_retries(self, task: Task) -> Task:
        revise_count = 0
        retry_count = 0

        while True:
            # ----- one attempt -----
            try:
                task = await asyncio.wait_for(run_task(task), timeout=self.timeout)
            except asyncio.TimeoutError:
                retry_count += 1
                await self._log(
                    task.id, "retry_timeout", {"attempt": retry_count}
                )
                log.warning(
                    "orchestrator.timeout",
                    task_id=str(task.id),
                    attempt=retry_count,
                )
                if retry_count > self.max_retries:
                    task.status = TaskStatus.FAILED
                    task.error = (
                        f"Pipeline timed out after {self.max_retries} retries."
                    )
                    await self._update(task)
                    await self._log(task.id, "failed", {"reason": "timeout"})
                    return task
                # Reset for retry
                task.status = TaskStatus.PENDING
                task.assigned_agent = None
                task.result = None
                await self._update(task)
                continue
            except Exception as exc:
                retry_count += 1
                await self._log(
                    task.id,
                    "retry_error",
                    {"attempt": retry_count, "error": str(exc)},
                )
                log.warning(
                    "orchestrator.error",
                    task_id=str(task.id),
                    attempt=retry_count,
                    error=str(exc),
                )
                if retry_count > self.max_retries:
                    task.status = TaskStatus.FAILED
                    task.error = f"Pipeline failed after {self.max_retries} retries: {exc}"
                    await self._update(task)
                    await self._log(task.id, "failed", {"reason": "error"})
                    return task
                task.status = TaskStatus.PENDING
                task.assigned_agent = None
                task.result = None
                await self._update(task)
                continue

            # ----- attempt succeeded; check for revise verdict -----
            qa_verdict = (
                task.result.artifacts.get("qa_verdict") if task.result else None
            )

            if (
                qa_verdict == "revise"
                and revise_count < self.revise_attempts
            ):
                revise_count += 1
                await self._log(
                    task.id, "revise_retry", {"attempt": revise_count}
                )
                log.info(
                    "orchestrator.revise_retry",
                    task_id=str(task.id),
                    attempt=revise_count,
                )
                # Clear result so the next attempt re-runs from scratch.
                # Phase 10 may keep the prior result on the messages log
                # so the re-run can see the previous attempt.
                task.status = TaskStatus.PENDING
                task.assigned_agent = None
                task.result = None
                await self._update(task)
                continue

            # ----- final -----
            await self._update(task)
            await self._log(
                task.id,
                "done",
                {
                    "final_status": task.status.value,
                    "assigned_agent": task.assigned_agent,
                    "retries": retry_count,
                    "revises": revise_count,
                    "qa_verdict": qa_verdict,
                },
            )
            return task

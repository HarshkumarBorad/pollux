"""Async repository for Task persistence.

The repository is the only layer that talks SQLAlchemy. Callers (the
orchestrator, the REST handlers, the UI) work with pydantic `Task` objects
and never see `TaskRecord`. Translation is centralized in `_to_task()` and
`_payload()`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import TaskEventRecord, TaskRecord
from core.tasks.models import Task, TaskStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TaskRepository:
    """CRUD for tasks + per-task event log. One repository instance per session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ----- create / read -----

    async def create(self, task: Task) -> None:
        """Insert a new task. Caller owns the pydantic Task; repository owns
        the row that mirrors it."""
        record = TaskRecord(
            id=str(task.id),
            type=task.type.value,
            status=task.status.value,
            assigned_agent=task.assigned_agent,
            payload_json=task.model_dump(mode="json"),
            retry_count=0,
            revise_count=0,
            error=task.error,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        self.session.add(record)
        await self.session.commit()

    async def get(self, task_id: UUID | str) -> Optional[Task]:
        record = await self.session.get(TaskRecord, str(task_id))
        if record is None:
            return None
        return self._to_task(record)

    async def list(
        self,
        status: Optional[TaskStatus] = None,
        assigned_agent: Optional[str] = None,
        limit: int = 50,
    ) -> list[Task]:
        stmt = select(TaskRecord).order_by(TaskRecord.updated_at.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(TaskRecord.status == status.value)
        if assigned_agent is not None:
            stmt = stmt.where(TaskRecord.assigned_agent == assigned_agent)
        result = await self.session.execute(stmt)
        return [self._to_task(r) for r in result.scalars().all()]

    # ----- update -----

    async def update(self, task: Task) -> None:
        """Rewrite the row to match the in-memory task. Updates the indexed
        columns + the payload blob together so they never disagree."""
        record = await self.session.get(TaskRecord, str(task.id))
        if record is None:
            raise ValueError(f"Task {task.id} not found")
        task.updated_at = _now()
        record.type = task.type.value
        record.status = task.status.value
        record.assigned_agent = task.assigned_agent
        record.error = task.error
        record.payload_json = task.model_dump(mode="json")
        record.updated_at = task.updated_at
        await self.session.commit()

    async def increment_retry(self, task_id: UUID | str) -> int:
        """Bump and return the new retry_count. Atomic under SQLite's
        per-transaction lock."""
        record = await self.session.get(TaskRecord, str(task_id))
        if record is None:
            raise ValueError(f"Task {task_id} not found")
        record.retry_count += 1
        record.updated_at = _now()
        await self.session.commit()
        return record.retry_count

    async def increment_revise(self, task_id: UUID | str) -> int:
        record = await self.session.get(TaskRecord, str(task_id))
        if record is None:
            raise ValueError(f"Task {task_id} not found")
        record.revise_count += 1
        record.updated_at = _now()
        await self.session.commit()
        return record.revise_count

    async def get_counters(self, task_id: UUID | str) -> tuple[int, int]:
        """Returns (retry_count, revise_count) for a task."""
        record = await self.session.get(TaskRecord, str(task_id))
        if record is None:
            raise ValueError(f"Task {task_id} not found")
        return record.retry_count, record.revise_count

    # ----- events -----

    async def log_event(
        self,
        task_id: UUID | str,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        event = TaskEventRecord(
            task_id=str(task_id),
            event_type=event_type,
            payload=payload or {},
            created_at=_now(),
        )
        self.session.add(event)
        await self.session.commit()

    async def list_events(self, task_id: UUID | str) -> list[TaskEventRecord]:
        stmt = (
            select(TaskEventRecord)
            .where(TaskEventRecord.task_id == str(task_id))
            .order_by(TaskEventRecord.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ----- internals -----

    def _to_task(self, record: TaskRecord) -> Task:
        """Deserialize the JSON payload back into a pydantic Task.

        Schema drift safety: pydantic parses the JSON afresh, so removing /
        adding optional fields in `Task` doesn't break already-stored rows.
        """
        return Task.model_validate(record.payload_json)

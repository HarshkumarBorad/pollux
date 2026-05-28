"""SQLAlchemy ORM models for task persistence.

Two tables:
    tasks         — current state of each task. The full pydantic Task is
                    serialized into `payload_json`; indexed columns
                    (`type`, `status`, `assigned_agent`, `updated_at`) are
                    duplicated as real columns for fast filtering.
    task_events   — append-only history of state transitions. Lets the UI
                    (Phase 9) show a per-task timeline without needing a
                    separate event-sourcing store.

Why JSON-blob the full pydantic instead of normalizing? Tasks have polymorphic
input (CustomerSupportInput | EmployeeQuestionInput | OpsWorkflowInput) and
nested messages/citations — modelling all of that as relational tables would
need 5+ joins per fetch and would need migrating whenever Task evolves. JSON
keeps the schema flat and the pydantic models stay the source of truth.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Single declarative base for all Pollux tables."""


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    assigned_agent: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )

    # Full pydantic Task serialization. Always in sync with the indexed cols
    # above (repository.update() rewrites them together).
    payload_json: Mapped[dict] = mapped_column(JSON)

    # Retry / loop counters tracked outside the payload so the orchestrator
    # doesn't have to deserialize the whole task to know how many attempts
    # have been made.
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    revise_count: Mapped[int] = mapped_column(Integer, default=0)

    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    events: Mapped[list["TaskEventRecord"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskEventRecord.created_at",
    )

    __table_args__ = (
        # Hot path: "show me the most recent tasks in this status" — UI inbox.
        Index("ix_tasks_status_updated", "status", "updated_at"),
    )


class TaskEventRecord(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    task: Mapped[TaskRecord] = relationship(back_populates="events")

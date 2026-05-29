"""Pydantic request / response schemas for the REST API.

Where a model is task-shape-specific (employee question vs customer ticket vs
ops workflow), we ship a tailored model. Generic task responses just re-use
`core.tasks.models.Task` directly — FastAPI handles the discriminated-union
serialization correctly because the model is pydantic v2 from end to end.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.tasks.models import Task, TaskStatus


# ----- submit requests --------------------------------------------------

class SubmitQuestionRequest(BaseModel):
    """POST /tasks/question — employee Q&A submission.

    Coordinator picks HR or IT specialist based on the question content."""

    question: str = Field(..., min_length=1, description="Natural-language employee question")
    employee_id: Optional[str] = Field(None, description="Optional employee identifier for audit")
    context: Optional[str] = Field(
        None, description="Optional prior-conversation context"
    )


class SubmitTicketRequest(BaseModel):
    """POST /tasks/ticket — customer support ticket submission.

    Routes to the Customer-Facing Specialist (two-stage: factual draft →
    tone-shifted rewrite)."""

    subject: str = Field(..., min_length=1, description="Ticket subject line")
    body: str = Field(..., min_length=1, description="Ticket body text")
    customer_id: Optional[str] = Field(None, description="Customer identifier for audit")
    channel: Literal["email", "web", "api"] = "web"


class SubmitMeetingRequest(BaseModel):
    """POST /tasks/meeting — ops workflow submission.

    Routes to the Ops Planner (summarize → structured subtasks)."""

    transcript: str = Field(..., min_length=1, description="Meeting transcript text")
    meeting_title: Optional[str] = Field("Untitled meeting", description="Display title")
    attendees: list[str] = Field(default_factory=list, description="Attendee names")


# ----- submit responses -------------------------------------------------

class SubmitResponse(BaseModel):
    """Returned by every submit endpoint regardless of sync / async mode."""

    task_id: UUID
    status: TaskStatus
    assigned_agent: Optional[str] = None
    sync: bool = Field(
        ..., description="True if the pipeline completed in this request (?wait=true)."
    )
    # Populated only when sync=True (the orchestrator awaited the pipeline).
    task: Optional[Task] = None
    # Convenience links for clients to poll / subscribe.
    location: str = Field(..., description="GET this URL for the task's current state.")
    stream: str = Field(..., description="WebSocket URL for live event subscription.")


# ----- listing / detail --------------------------------------------------

class TaskListResponse(BaseModel):
    tasks: list[Task]
    count: int


class TaskEventOut(BaseModel):
    """A single row from the task_events table, JSON-serializable."""

    id: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class TaskDetailResponse(BaseModel):
    task: Task
    events: list[TaskEventOut]


# ----- discovery / health ------------------------------------------------

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["connected", "unreachable"]
    agents: int = Field(..., description="Number of registered agents")


# ----- WebSocket event envelope ------------------------------------------

class WSEvent(BaseModel):
    """Envelope for every message the WebSocket emits to the client.

    `type` discriminates:
        - "status" : Initial task snapshot when the WS connects.
        - "event"  : An entry from the task_events log.
        - "result" : Final task state when it reaches a terminal status.
        - "error"  : Something went wrong on the server side.
    """

    type: Literal["status", "event", "result", "error"]
    data: dict[str, Any]

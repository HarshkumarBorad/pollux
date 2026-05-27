"""Canonical task / message / agent-card data models.

These shapes flow between agents regardless of orchestration variant. The MCP
variant serializes them as tool args / results; the A2A variant maps them onto
the A2A Task / Message envelope. The in-memory types are identical either way.

Design notes:
- `TaskInputUnion` is a tagged union (`task_type` is the discriminator). Pydantic
  picks the right concrete subclass at parse time, so a single `Task.parse_obj()`
  handles all three task domains without manual switching.
- `AgentCard` doubles as (a) Pollux's internal agent registry entry, (b) a
  FastMCP tool definition (Phase 6), (c) the basis for an A2A Agent Card
  (Phase 7). One source of truth, multiple wire formats.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----- Task type / status / message role enums ---------------------------

class TaskType(str, Enum):
    """The three task domains Pollux automates."""

    CUSTOMER_SUPPORT = "customer_support"
    EMPLOYEE_QUESTION = "employee_question"
    OPS_WORKFLOW = "ops_workflow"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNED = "planned"  # Coordinator has decided what to do, work not started
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"  # Punted to a human


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# ----- Citation ----------------------------------------------------------

class Citation(BaseModel):
    """A reference back to a knowledge source used in an answer."""

    source: str
    text: str
    score: Optional[float] = None
    domain: Optional[str] = None  # which knowledge subset (hr / tech / product / ...)


# ----- Inter-agent / user message ----------------------------------------

class Message(BaseModel):
    """A single turn of inter-agent or agent-user communication."""

    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    from_agent: str  # e.g. "user", "coordinator", "hr_specialist"
    to_agent: str
    role: MessageRole
    content: str
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


# ----- Capability + AgentCard (the cross-protocol "what this agent does") -

class CapabilityExample(BaseModel):
    """A concrete input/output pair — used in LLM prompts and A2A cards."""

    input: dict[str, Any]
    output: dict[str, Any]
    description: Optional[str] = None


class Capability(BaseModel):
    """Single thing an agent can do. JSON-Schema-typed for protocol-friendly
    serialization (MCP tool def, A2A capability)."""

    name: str
    description: str
    input_schema: dict[str, Any]   # JSON Schema for inputs
    output_schema: dict[str, Any]  # JSON Schema for outputs
    examples: list[CapabilityExample] = Field(default_factory=list)


class AgentCard(BaseModel):
    """Discoverable description of an agent. Same data, different wire format
    per orchestration variant.

    MCP serializes each Capability as a separate tool. A2A serializes the whole
    card as the agent's discovery document.
    """

    id: str  # stable identifier, e.g. "hr_specialist"
    name: str  # display name, e.g. "HR Specialist"
    description: str
    capabilities: list[Capability]
    supported_task_types: list[TaskType]
    version: str = "0.1.0"


# ----- Task inputs (polymorphic, tagged union) ---------------------------

class CustomerSupportInput(BaseModel):
    task_type: Literal[TaskType.CUSTOMER_SUPPORT] = TaskType.CUSTOMER_SUPPORT
    ticket_subject: str
    ticket_body: str
    customer_id: Optional[str] = None
    channel: Literal["email", "web", "api"] = "web"


class EmployeeQuestionInput(BaseModel):
    task_type: Literal[TaskType.EMPLOYEE_QUESTION] = TaskType.EMPLOYEE_QUESTION
    question: str
    employee_id: Optional[str] = None
    context: Optional[str] = None  # prior conversation, etc.


class OpsWorkflowInput(BaseModel):
    task_type: Literal[TaskType.OPS_WORKFLOW] = TaskType.OPS_WORKFLOW
    transcript: str
    meeting_title: Optional[str] = None
    attendees: list[str] = Field(default_factory=list)


TaskInputUnion = Annotated[
    Union[CustomerSupportInput, EmployeeQuestionInput, OpsWorkflowInput],
    Field(discriminator="task_type"),
]


# ----- TaskResult --------------------------------------------------------

class TaskResult(BaseModel):
    """The final answer / outcome produced by an agent for a task."""

    summary: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    # task-type-specific keys, e.g.:
    #   customer_support: {"draft_reply": "...", "suggested_priority": "high"}
    #   ops_workflow:     {"action_items": [{"task": "...", "assignee": "..."}]}
    citations: list[Citation] = Field(default_factory=list)
    confidence: Optional[float] = None  # 0..1, set by Escalation Agent


# ----- Task (the unit-of-work envelope) ----------------------------------

class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING

    input: TaskInputUnion
    result: Optional[TaskResult] = None
    error: Optional[str] = None

    assigned_agent: Optional[str] = None
    parent_task_id: Optional[UUID] = None  # for sub-tasks under an Ops Planner

    messages: list[Message] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

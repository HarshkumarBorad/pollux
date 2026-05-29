"""A2A AgentExecutor implementations for Pollux.

`PolluxAgentExecutor` wraps a single Pollux specialist as an A2A executor:
receives an A2A Message, converts it to a Pollux Task, runs the agent,
emits the result as an A2A Message back into the event queue.

`CoordinatorExecutor` is the special case for the Coordinator endpoint —
runs the FULL pipeline via `TaskOrchestrator.submit()` (with DB persistence)
rather than the agent's routing decision alone.

Both extract structured input from incoming Messages in this priority order:
    1. DataPart — preferred (the intended A2A pattern)
    2. TextPart that contains valid JSON
    3. TextPart with raw text — treated as `{"text": "..."}`

True streaming (chunk-by-chunk LLM output) is a Phase 10 polish item; for
now we await the full agent run and emit a single Message at the end.
"""
from __future__ import annotations

import json
from typing import Any

from a2a.helpers.proto_helpers import (
    get_data_parts,
    get_text_parts,
    new_text_message,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

from agents import BaseAgent
from core.tasks.models import (
    CustomerSupportInput,
    EmployeeQuestionInput,
    OpsWorkflowInput,
    Task,
    TaskType,
)
from core.telemetry import get_logger

log = get_logger("pollux.a2a.executor")


def _extract_input(context: RequestContext) -> dict[str, Any]:
    """Pull a structured dict from the incoming A2A message."""
    message = context.message
    if message is None or not message.parts:
        return {}

    parts = list(message.parts)

    # Prefer DataPart — already deserialized to dict/list by the helper.
    for data in get_data_parts(parts):
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass

    # Fall back to TextPart, concatenated.
    text = "\n".join(get_text_parts(parts)).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"text": str(parsed)}
    except (json.JSONDecodeError, ValueError):
        return {"text": text}


def _build_task_for_type(task_type: TaskType, input_data: dict) -> Task:
    """Build the right pydantic Task subclass from extracted A2A input."""
    if task_type == TaskType.EMPLOYEE_QUESTION:
        question = input_data.get("question") or input_data.get("text", "")
        return Task(
            type=task_type,
            input=EmployeeQuestionInput(question=question),
        )
    if task_type == TaskType.CUSTOMER_SUPPORT:
        return Task(
            type=task_type,
            input=CustomerSupportInput(
                ticket_subject=(
                    input_data.get("ticket_subject")
                    or input_data.get("subject", "")
                ),
                ticket_body=(
                    input_data.get("ticket_body")
                    or input_data.get("body", "")
                ),
            ),
        )
    if task_type == TaskType.OPS_WORKFLOW:
        return Task(
            type=task_type,
            input=OpsWorkflowInput(
                transcript=input_data.get("transcript", ""),
                meeting_title=input_data.get("meeting_title", "Untitled meeting"),
                attendees=input_data.get("attendees", []),
            ),
        )
    raise ValueError(f"Cannot build task for type {task_type!r}")


class PolluxAgentExecutor(AgentExecutor):
    """Generic executor — wraps any Pollux specialist."""

    def __init__(self, agent: BaseAgent) -> None:
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        input_data = _extract_input(context)
        if not self.agent.supported_task_types:
            await event_queue.enqueue_event(
                new_text_message(
                    f"ERROR: Agent {self.agent.id!r} has no supported_task_types."
                )
            )
            return
        try:
            task = _build_task_for_type(
                self.agent.supported_task_types[0], input_data
            )
        except Exception as exc:
            await event_queue.enqueue_event(
                new_text_message(f"ERROR: Could not build task: {exc}")
            )
            return

        log.info(
            "a2a.execute_start",
            agent=self.agent.id,
            task_type=task.type.value,
        )
        try:
            result = await self.agent.run(task)
        except Exception as exc:
            log.error("a2a.agent_error", agent=self.agent.id, error=str(exc))
            await event_queue.enqueue_event(
                new_text_message(f"ERROR: {self.agent.id} failed: {exc}")
            )
            return

        await event_queue.enqueue_event(new_text_message(result.summary))
        log.info(
            "a2a.execute_done",
            agent=self.agent.id,
            chars=len(result.summary or ""),
            confidence=result.confidence,
            citations=len(result.citations or []),
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Pollux agents have no cancellation primitive yet."""
        await event_queue.enqueue_event(
            new_text_message("Cancellation is not supported for this agent.")
        )


class CoordinatorExecutor(AgentExecutor):
    """Runs the FULL pipeline through `TaskOrchestrator.submit()` —
    Coordinator → Specialist → Escalation, persisted to SQLite. The headline
    A2A endpoint for clients that want "submit a task, get a final answer"
    semantics."""

    def __init__(self) -> None:
        from agents.coordinator import CoordinatorAgent
        self.agent = CoordinatorAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        from orchestrator import TaskOrchestrator

        input_data = _extract_input(context)
        task = self._infer_task(input_data)
        if task is None:
            await event_queue.enqueue_event(
                new_text_message(
                    "ERROR: Could not determine task type from input. Provide a "
                    "DataPart with one of:\n"
                    "  {'question': '...'}                        — employee question\n"
                    "  {'subject': '...', 'body': '...'}          — customer ticket\n"
                    "  {'transcript': '...', 'attendees': [...]}  — meeting transcript"
                )
            )
            return

        log.info("a2a.coordinator_start", task_type=task.type.value)
        try:
            final = await TaskOrchestrator().submit(task)
        except Exception as exc:
            log.error("a2a.coordinator_error", error=str(exc))
            await event_queue.enqueue_event(
                new_text_message(f"ERROR: Pipeline failed: {exc}")
            )
            return

        summary_lines = [
            f"Status      : {final.status.value}",
            f"Routed to   : {final.assigned_agent or '-'}",
        ]
        if final.error:
            summary_lines.append(f"Error       : {final.error}")
        if final.result is not None:
            verdict = final.result.artifacts.get("qa_verdict", "n/a")
            summary_lines.append(f"QA verdict  : {verdict}")
            summary_lines.append(f"Confidence  : {final.result.confidence}")
            summary_lines.append("")
            summary_lines.append(final.result.summary or "(no summary)")
        await event_queue.enqueue_event(
            new_text_message("\n".join(summary_lines))
        )
        log.info(
            "a2a.coordinator_done",
            task_id=str(final.id),
            final_status=final.status.value,
            assigned_agent=final.assigned_agent,
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(
            new_text_message("Cancellation is not supported.")
        )

    def _infer_task(self, input_data: dict) -> Task | None:
        """Sniff the task type from the input shape — Coordinator accepts any."""
        if "transcript" in input_data:
            return _build_task_for_type(TaskType.OPS_WORKFLOW, input_data)
        if "subject" in input_data or "ticket_subject" in input_data:
            return _build_task_for_type(TaskType.CUSTOMER_SUPPORT, input_data)
        if "question" in input_data or "text" in input_data:
            return _build_task_for_type(TaskType.EMPLOYEE_QUESTION, input_data)
        return None

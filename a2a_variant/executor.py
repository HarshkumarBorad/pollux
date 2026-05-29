"""A2A AgentExecutor implementations for Pollux.

`PolluxAgentExecutor` — wraps a single Pollux specialist as an A2A executor.
                       Receives an A2A message, converts it to a Pollux Task,
                       runs the agent, emits the result as an A2A event.

`CoordinatorExecutor` — special-case executor for the Coordinator endpoint.
                       Uses `TaskOrchestrator.submit()` so the full
                       Coordinator → Specialist → Escalation pipeline runs
                       (with DB persistence), not just the Coordinator's
                       routing decision.

Streaming is partial in Phase 7: we await the full agent run before emitting
a single result event. True intra-graph streaming (Coordinator picks → emit
event → Specialist streams chunks → ...) is a Phase 10 polish item.
"""
from __future__ import annotations

import json
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import DataPart, Message, TextPart
from a2a.utils import new_agent_text_message

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


def _unwrap_part(part: Any) -> Any:
    """A2A SDK wraps Part-union in `.root` for some pydantic versions; this
    handles both wrapped and unwrapped instances."""
    return getattr(part, "root", part)


def _extract_input(context: RequestContext) -> dict[str, Any]:
    """Pull a structured dict from the incoming A2A message.

    Order of preference:
    1. DataPart       — structured JSON. The intended A2A pattern.
    2. TextPart       — JSON-encoded string. Lower-friction for curl/HTTP
                        clients that don't know about DataPart.
    3. TextPart       — raw text. Returned as `{"text": "..."}` so the
                        per-agent task builder can decide how to use it.
    """
    if context.message is None or not context.message.parts:
        return {}

    # Prefer DataPart.
    for part in context.message.parts:
        unwrapped = _unwrap_part(part)
        if isinstance(unwrapped, DataPart):
            return dict(unwrapped.data or {})

    # Concatenate TextParts.
    text_chunks: list[str] = []
    for part in context.message.parts:
        unwrapped = _unwrap_part(part)
        if isinstance(unwrapped, TextPart):
            text_chunks.append(unwrapped.text)
    text = "".join(text_chunks).strip()

    if not text:
        return {}

    # Try JSON first; fall back to raw text.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"text": str(parsed)}
    except (json.JSONDecodeError, ValueError):
        return {"text": text}


def _build_task_for_type(task_type: TaskType, input_data: dict) -> Task:
    """Build the right pydantic Task subclass given the agent's task type
    and an extracted input dict."""
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
    """Generic executor — wraps any Pollux specialist agent."""

    def __init__(self, agent: BaseAgent) -> None:
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        input_data = _extract_input(context)
        if not self.agent.supported_task_types:
            await event_queue.enqueue_event(
                new_agent_text_message(
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
                new_agent_text_message(f"ERROR: Could not build task: {exc}")
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
                new_agent_text_message(f"ERROR: {self.agent.id} failed: {exc}")
            )
            return

        await event_queue.enqueue_event(new_agent_text_message(result.summary))
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
            new_agent_text_message("Cancellation is not supported for this agent.")
        )


class CoordinatorExecutor(AgentExecutor):
    """Coordinator endpoint — runs the FULL pipeline through the orchestrator
    (with DB persistence) rather than just the routing-decision step.

    This is the headline A2A endpoint for clients that want "submit a task,
    get a final answer." Equivalent to `submit_*` MCP tools combined.
    """

    def __init__(self) -> None:
        from agents.coordinator import CoordinatorAgent
        self.agent = CoordinatorAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        from orchestrator import TaskOrchestrator

        input_data = _extract_input(context)
        task = self._infer_task(input_data)
        if task is None:
            await event_queue.enqueue_event(
                new_agent_text_message(
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
                new_agent_text_message(f"ERROR: Pipeline failed: {exc}")
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
            new_agent_text_message("\n".join(summary_lines))
        )
        log.info(
            "a2a.coordinator_done",
            task_id=str(final.id),
            final_status=final.status.value,
            assigned_agent=final.assigned_agent,
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(
            new_agent_text_message("Cancellation is not supported.")
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

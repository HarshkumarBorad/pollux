"""MCP tools wrapping Pollux agents + orchestrator.

Tool naming convention:
    submit_*    — full pipeline (Coordinator → Specialist → Escalation),
                   persisted to the task store.
    query_/draft_/plan_  — direct agent invocation, no orchestrator, no DB.
                          Faster, but no audit trail.
    list_/get_  — read-only operations.

Tool docstrings are written for the calling LLM (Claude Desktop, Cline,
Cursor, etc.) — they are what the agent client sees when deciding which
tool to call. Keep them action-oriented and include "use this when" hints.
"""
from __future__ import annotations

from typing import Any, Optional

from fastmcp import FastMCP

from agents import get_agent, list_agent_cards
from core.tasks.models import (
    CustomerSupportInput,
    EmployeeQuestionInput,
    OpsWorkflowInput,
    Task,
    TaskResult,
    TaskStatus,
    TaskType,
)
from orchestrator import TaskOrchestrator


def register_tools(mcp: FastMCP) -> None:
    """Attach every Pollux MCP tool to the given FastMCP server instance."""

    # ----- submit_* (orchestrated + persisted) -----

    @mcp.tool()
    async def submit_employee_question(question: str) -> dict:
        """Submit an employee question to Pollux. Coordinator picks HR or IT
        specialist based on topic, runs the answer, has the Escalation/QA
        agent review it, and persists the whole flow to the task store.

        Use this when an employee asks a question and you want the full
        multi-agent treatment (routing + answer + QA verdict).

        Returns the final task — `status` is `completed` (ship the answer)
        or `escalated` (route to a human). Specialist's answer lives in
        `result.summary` with citations in `result.citations`.
        """
        task = Task(
            type=TaskType.EMPLOYEE_QUESTION,
            input=EmployeeQuestionInput(question=question),
        )
        final = await TaskOrchestrator().submit(task)
        return _task_to_dict(final)

    @mcp.tool()
    async def submit_customer_ticket(subject: str, body: str) -> dict:
        """Submit a customer support ticket. Customer-Facing Specialist
        drafts a factual reply (with internal citations) and then rewrites
        it in a customer-friendly tone. Escalation reviews. Persisted.

        Use this when a customer's ticket lands and you want a ready-to-send
        reply draft. The polished reply is in `result.summary`; the internal
        draft (citations intact, for QA) is in `result.artifacts.internal_draft`.
        """
        task = Task(
            type=TaskType.CUSTOMER_SUPPORT,
            input=CustomerSupportInput(ticket_subject=subject, ticket_body=body),
        )
        final = await TaskOrchestrator().submit(task)
        return _task_to_dict(final)

    @mcp.tool()
    async def submit_ops_workflow(
        transcript: str,
        meeting_title: str = "Untitled meeting",
        attendees: Optional[list[str]] = None,
    ) -> dict:
        """Submit a meeting transcript. Ops Planner summarizes it and
        extracts structured action items (task, assignee, priority, deadline).
        Persisted.

        Use this after any internal meeting whose decisions should turn into
        trackable tasks. Action items are in `result.artifacts.subtasks`;
        the summary bullet-points are in `result.summary`.
        """
        task = Task(
            type=TaskType.OPS_WORKFLOW,
            input=OpsWorkflowInput(
                transcript=transcript,
                meeting_title=meeting_title,
                attendees=attendees or [],
            ),
        )
        final = await TaskOrchestrator().submit(task)
        return _task_to_dict(final)

    # ----- direct (no orchestrator, no persistence) -----

    @mcp.tool()
    async def query_hr(question: str) -> dict:
        """Directly query the HR Specialist — no Coordinator routing, no
        Escalation QA, no DB persistence. Faster than `submit_employee_question`
        but no audit trail.

        Use this when you've already classified the question as HR-flavored
        (leave, payroll, onboarding, code of conduct, etc.) and want the
        answer immediately.
        """
        return await _run_specialist_direct("hr_specialist", question)

    @mcp.tool()
    async def query_it(question: str) -> dict:
        """Directly query the IT/Tech Specialist (no orchestration, no
        persistence).

        Use this for already-classified technical questions: API references,
        SDK usage, programming, DevOps, infrastructure.
        """
        return await _run_specialist_direct("it_specialist", question)

    @mcp.tool()
    async def draft_customer_reply(subject: str, body: str) -> dict:
        """Directly invoke the Customer-Facing Specialist (no orchestration,
        no persistence).

        Returns the two-stage output — `artifacts.internal_draft` is the
        cited factual draft, `summary` is the customer-ready rewrite.
        """
        agent = get_agent("customer_facing")
        task = Task(
            type=TaskType.CUSTOMER_SUPPORT,
            input=CustomerSupportInput(ticket_subject=subject, ticket_body=body),
        )
        return _result_to_dict(await agent.run(task))

    @mcp.tool()
    async def plan_from_meeting(
        transcript: str,
        meeting_title: str = "Untitled meeting",
        attendees: Optional[list[str]] = None,
    ) -> dict:
        """Directly invoke the Ops Planner (no orchestration, no persistence).

        Returns summary + structured subtasks. Same shape as
        `submit_ops_workflow.result` but without the surrounding task
        envelope.
        """
        agent = get_agent("ops_planner")
        task = Task(
            type=TaskType.OPS_WORKFLOW,
            input=OpsWorkflowInput(
                transcript=transcript,
                meeting_title=meeting_title,
                attendees=attendees or [],
            ),
        )
        return _result_to_dict(await agent.run(task))

    # ----- discovery / inspection -----

    @mcp.tool()
    async def list_agents() -> list[dict]:
        """List all six registered agents with their capabilities and the
        knowledge domain each one owns.

        Call this first if you're unsure which agent or `submit_*` tool to
        use. Returns agent cards in the same shape Phase 7's A2A variant
        will serve at its discovery endpoint.
        """
        return [card.model_dump(mode="json") for card in list_agent_cards()]

    @mcp.tool()
    async def get_task_status(task_id: str) -> dict:
        """Get the current state of a previously submitted task by ID.

        Returns the same task envelope as `submit_*`. Use this to poll
        the result of a long-running task that you submitted async, or
        to inspect what an old task looks like in the audit log.
        """
        task = await TaskOrchestrator().get(task_id)
        if task is None:
            return {"error": f"Task {task_id} not found"}
        return _task_to_dict(task)

    @mcp.tool()
    async def list_tasks(
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """List recently submitted tasks. Optionally filter by status.

        Valid statuses: `pending`, `planned`, `in_progress`, `completed`,
        `failed`, `escalated`.
        """
        status_enum = TaskStatus(status) if status else None
        tasks = await TaskOrchestrator().list(status=status_enum, limit=limit)
        return [_task_to_dict(t) for t in tasks]


# ----- helpers ----------------------------------------------------------

async def _run_specialist_direct(agent_id: str, question: str) -> dict:
    agent = get_agent(agent_id)
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question=question),
    )
    result = await agent.run(task)
    return _result_to_dict(result)


def _task_to_dict(task: Task) -> dict[str, Any]:
    return task.model_dump(mode="json")


def _result_to_dict(result: TaskResult) -> dict[str, Any]:
    return result.model_dump(mode="json")

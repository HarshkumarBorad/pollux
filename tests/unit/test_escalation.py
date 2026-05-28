"""Escalation / QA verdict tests.

Pure rule-based logic — no LLM, no network. Phase 10 will add LLM-as-judge
tests that go through the network and are gated on HF_TOKEN.
"""
from __future__ import annotations

import pytest

from agents.escalation import (
    ESCALATE_BELOW,
    NO_INFO_MARKERS,
    REVISE_BELOW,
    EscalationAgent,
)
from core.tasks import (
    EmployeeQuestionInput,
    Task,
    TaskResult,
    TaskType,
)


def _task_with_result(result: TaskResult | None, error: str | None = None) -> Task:
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question="?"),
    )
    task.result = result
    task.error = error
    return task


@pytest.mark.asyncio
async def test_no_result_escalates() -> None:
    agent = EscalationAgent()
    task = _task_with_result(None)
    out = await agent.run(task)
    assert out.artifacts["verdict"] == "escalate"


@pytest.mark.asyncio
async def test_task_with_error_escalates() -> None:
    agent = EscalationAgent()
    task = _task_with_result(
        TaskResult(summary="partial", confidence=0.9),
        error="upstream service timed out",
    )
    out = await agent.run(task)
    assert out.artifacts["verdict"] == "escalate"
    assert "upstream service timed out" in out.summary


@pytest.mark.asyncio
async def test_no_info_marker_escalates() -> None:
    agent = EscalationAgent()
    # Use the first NO_INFO_MARKER directly so the test stays in sync if the
    # marker text ever changes.
    marker = NO_INFO_MARKERS[0]
    task = _task_with_result(
        TaskResult(summary=f"{marker} — sorry.", confidence=0.95),
    )
    out = await agent.run(task)
    assert out.artifacts["verdict"] == "escalate"


@pytest.mark.asyncio
async def test_low_confidence_escalates() -> None:
    agent = EscalationAgent()
    task = _task_with_result(
        TaskResult(summary="something", confidence=ESCALATE_BELOW - 0.01),
    )
    out = await agent.run(task)
    assert out.artifacts["verdict"] == "escalate"


@pytest.mark.asyncio
async def test_medium_confidence_revises() -> None:
    agent = EscalationAgent()
    task = _task_with_result(
        TaskResult(summary="something", confidence=(ESCALATE_BELOW + REVISE_BELOW) / 2),
    )
    out = await agent.run(task)
    assert out.artifacts["verdict"] == "revise"


@pytest.mark.asyncio
async def test_high_confidence_ships() -> None:
    agent = EscalationAgent()
    task = _task_with_result(
        TaskResult(summary="answer", confidence=0.9),
    )
    out = await agent.run(task)
    assert out.artifacts["verdict"] == "ship"


@pytest.mark.asyncio
async def test_adjusted_confidence_preserved_through_verdict() -> None:
    """The verdict should not invent a confidence; it propagates whatever the
    specialist reported (or 0.0 / 0.2 for the error / no-info cases)."""
    agent = EscalationAgent()
    task = _task_with_result(
        TaskResult(summary="answer", confidence=0.92),
    )
    out = await agent.run(task)
    assert out.confidence == pytest.approx(0.92)
    assert out.artifacts["adjusted_confidence"] == pytest.approx(0.92)

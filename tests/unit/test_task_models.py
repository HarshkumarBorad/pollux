"""Unit tests for the core task data models.

These tests are the contract between every later phase — if any phase breaks
how Task / Message / AgentCard serialize, CI catches it here.

Run with:
    pytest tests/unit/test_task_models.py
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from core.tasks import (
    AgentCard,
    Capability,
    Citation,
    CustomerSupportInput,
    EmployeeQuestionInput,
    Message,
    MessageRole,
    OpsWorkflowInput,
    Task,
    TaskResult,
    TaskStatus,
    TaskType,
)


def test_customer_support_task_roundtrip() -> None:
    task = Task(
        type=TaskType.CUSTOMER_SUPPORT,
        input=CustomerSupportInput(
            ticket_subject="API 401s",
            ticket_body="Token rotated, getting 401.",
            customer_id="cust_42",
        ),
    )
    parsed = Task.model_validate_json(task.model_dump_json())
    assert parsed.id == task.id
    assert isinstance(parsed.input, CustomerSupportInput)
    assert parsed.input.ticket_subject == "API 401s"


def test_employee_question_task_roundtrip() -> None:
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question="How many vacation days?"),
    )
    parsed = Task.model_validate_json(task.model_dump_json())
    assert isinstance(parsed.input, EmployeeQuestionInput)
    assert parsed.input.question == "How many vacation days?"


def test_ops_workflow_task_roundtrip() -> None:
    task = Task(
        type=TaskType.OPS_WORKFLOW,
        input=OpsWorkflowInput(
            transcript="Discussed billing migration timeline.",
            meeting_title="Platform weekly",
            attendees=["Lina", "Marc"],
        ),
    )
    parsed = Task.model_validate_json(task.model_dump_json())
    assert isinstance(parsed.input, OpsWorkflowInput)
    assert "billing" in parsed.input.transcript


def test_discriminator_resolves_correctly_from_raw_json() -> None:
    """Tagged-union must pick the right subclass from `task_type` alone."""
    raw = json.dumps(
        {
            "type": "employee_question",
            "input": {
                "task_type": "employee_question",
                "question": "What's the leave policy?",
            },
        }
    )
    task = Task.model_validate_json(raw)
    assert isinstance(task.input, EmployeeQuestionInput)


def test_invalid_task_type_rejected() -> None:
    with pytest.raises(Exception):
        Task.model_validate_json(
            json.dumps(
                {
                    "type": "employee_question",
                    "input": {"task_type": "not_a_real_type", "question": "x"},
                }
            )
        )


def test_message_roundtrip_with_citations() -> None:
    task_id = uuid4()
    msg = Message(
        task_id=task_id,
        from_agent="hr_specialist",
        to_agent="user",
        role=MessageRole.ASSISTANT,
        content="You're entitled to 30 days [1].",
        citations=[Citation(source="handbook.pdf", text="30 working days...", score=0.92)],
    )
    parsed = Message.model_validate_json(msg.model_dump_json())
    assert parsed.task_id == task_id
    assert len(parsed.citations) == 1
    assert parsed.citations[0].score == pytest.approx(0.92)


def test_agent_card_roundtrip() -> None:
    card = AgentCard(
        id="hr_specialist",
        name="HR Specialist",
        description="HR Q&A.",
        capabilities=[
            Capability(
                name="answer_hr_question",
                description="Answer an HR question.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        ],
        supported_task_types=[TaskType.EMPLOYEE_QUESTION],
    )
    parsed = AgentCard.model_validate_json(card.model_dump_json())
    assert parsed.id == "hr_specialist"
    assert parsed.capabilities[0].name == "answer_hr_question"
    assert TaskType.EMPLOYEE_QUESTION in parsed.supported_task_types


def test_task_result_with_artifacts() -> None:
    """TaskResult.artifacts is intentionally schemaless — each task type fills
    in keys appropriate to its domain. Sanity-check the dict round-trips."""
    result = TaskResult(
        summary="Drafted a reply.",
        artifacts={"draft_reply": "Dear customer, ...", "suggested_priority": "high"},
        confidence=0.85,
    )
    parsed = TaskResult.model_validate_json(result.model_dump_json())
    assert parsed.artifacts["suggested_priority"] == "high"
    assert parsed.confidence == pytest.approx(0.85)


def test_task_status_default_pending() -> None:
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question="?"),
    )
    assert task.status == TaskStatus.PENDING

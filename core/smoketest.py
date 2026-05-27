"""Smoke test — verifies the Phase 1 scaffold imports and round-trips models.

Run with:
    python -m core.smoketest

Used as the Dockerfile's default CMD until Phase 8 wires up real services.
"""
from __future__ import annotations

import json
import sys
from uuid import uuid4

from core import telemetry
from core.config import get_config
from core.tasks import (
    AgentCard,
    Capability,
    CustomerSupportInput,
    EmployeeQuestionInput,
    Message,
    MessageRole,
    OpsWorkflowInput,
    Task,
    TaskStatus,
    TaskType,
)


def _sample_tasks() -> list[Task]:
    """One example of each task type — exercises the discriminated union."""
    return [
        Task(
            type=TaskType.CUSTOMER_SUPPORT,
            input=CustomerSupportInput(
                ticket_subject="API key not working",
                ticket_body="I rotated my key yesterday and now get 401s.",
                customer_id="cust_42",
                channel="email",
            ),
        ),
        Task(
            type=TaskType.EMPLOYEE_QUESTION,
            input=EmployeeQuestionInput(
                question="How many vacation days do I get per year?",
                employee_id="emp_007",
            ),
        ),
        Task(
            type=TaskType.OPS_WORKFLOW,
            input=OpsWorkflowInput(
                transcript="Lina: Let's ship the billing migration this sprint...",
                meeting_title="Platform weekly",
                attendees=["Lina Schmidt", "Marc Weber"],
            ),
        ),
    ]


def _sample_card() -> AgentCard:
    return AgentCard(
        id="hr_specialist",
        name="HR Specialist",
        description="Answers HR / policy / onboarding questions with citations.",
        capabilities=[
            Capability(
                name="answer_hr_question",
                description="Answer an employee's HR question using internal docs.",
                input_schema={
                    "type": "object",
                    "required": ["question"],
                    "properties": {"question": {"type": "string"}},
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "citations": {"type": "array"},
                    },
                },
            )
        ],
        supported_task_types=[TaskType.EMPLOYEE_QUESTION],
    )


def main() -> int:
    telemetry.init()
    log = telemetry.get_logger("smoketest")
    tracer = telemetry.get_tracer("smoketest")

    config = get_config()
    log.info(
        "pollux.smoketest.start",
        app_env=config.app_env,
        orchestration=config.pollux_orchestration,
        hf_token_set=bool(config.hf_token),
        openai_enabled=config.openai_enabled,
    )

    # Exercise the tagged-union task input parsing in both directions.
    with tracer.start_as_current_span("smoketest.tasks"):
        tasks = _sample_tasks()
        for task in tasks:
            roundtrip = Task.model_validate_json(task.model_dump_json())
            assert roundtrip.id == task.id
            assert roundtrip.input.task_type == task.input.task_type
            log.info(
                "task.roundtrip_ok",
                task_id=str(task.id),
                task_type=task.type.value,
                input_type=type(task.input).__name__,
            )

    # Exercise message + AgentCard.
    with tracer.start_as_current_span("smoketest.message_and_card"):
        task_id = tasks[1].id
        msg = Message(
            task_id=task_id,
            from_agent="coordinator",
            to_agent="hr_specialist",
            role=MessageRole.ASSISTANT,
            content="Please answer this HR question.",
        )
        msg_roundtrip = Message.model_validate_json(msg.model_dump_json())
        assert msg_roundtrip.task_id == task_id

        card = _sample_card()
        card_roundtrip = AgentCard.model_validate_json(card.model_dump_json())
        assert card_roundtrip.capabilities[0].name == "answer_hr_question"
        log.info("agent_card.roundtrip_ok", agent_id=card.id, capability_count=len(card.capabilities))

    # Show what a serialized task looks like — useful for spotting schema drift early.
    sample_json = json.loads(tasks[0].model_dump_json())
    sample_json["id"] = str(sample_json["id"])  # for display
    log.info("sample_task_shape", task=sample_json)

    log.info("pollux.smoketest.ok", tasks_validated=len(tasks))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Test the static metadata + agent-card surface of every agent.

These tests never instantiate the agents — they exercise the class-level
attributes only. Safe to run without HF_TOKEN or ChromaDB.
"""
from __future__ import annotations

import pytest

from agents import (
    AGENT_REGISTRY,
    CustomerFacingSpecialist,
    HRSpecialist,
    ITSpecialist,
    OpsPlanner,
    list_agent_cards,
)
from core.knowledge import KnowledgeDomain
from core.tasks import AgentCard, TaskType


@pytest.mark.parametrize(
    "cls", [HRSpecialist, ITSpecialist, CustomerFacingSpecialist, OpsPlanner]
)
def test_required_metadata_set(cls) -> None:
    assert cls.id, f"{cls.__name__} must set `id`"
    assert cls.name, f"{cls.__name__} must set `name`"
    assert cls.description, f"{cls.__name__} must set `description`"
    assert cls.capabilities, f"{cls.__name__} must declare capabilities"
    assert cls.supported_task_types, f"{cls.__name__} must set supported_task_types"


@pytest.mark.parametrize(
    "cls", [HRSpecialist, ITSpecialist, CustomerFacingSpecialist, OpsPlanner]
)
def test_agent_card_roundtrips(cls) -> None:
    card = cls.agent_card()
    assert isinstance(card, AgentCard)
    assert card.id == cls.id
    assert card.name == cls.name
    assert card.capabilities, "card must include at least one capability"
    # JSON round-trip — important for both MCP tool emission and A2A.
    parsed = AgentCard.model_validate_json(card.model_dump_json())
    assert parsed.id == card.id


def test_registry_keys_match_class_ids() -> None:
    """The registry key must match the class's `id` attribute — otherwise
    `get_agent("hr_specialist")` returns nothing or the wrong agent."""
    for agent_id, cls in AGENT_REGISTRY.items():
        assert agent_id == cls.id


def test_specialist_domains() -> None:
    assert HRSpecialist.domain == KnowledgeDomain.HR
    assert ITSpecialist.domain == KnowledgeDomain.IT
    assert CustomerFacingSpecialist.domain == KnowledgeDomain.PRODUCT
    # Ops Planner is intentionally domain-less — works from the transcript only.
    assert OpsPlanner.domain is None


def test_supported_task_types() -> None:
    assert TaskType.EMPLOYEE_QUESTION in HRSpecialist.supported_task_types
    assert TaskType.EMPLOYEE_QUESTION in ITSpecialist.supported_task_types
    assert TaskType.CUSTOMER_SUPPORT in CustomerFacingSpecialist.supported_task_types
    assert TaskType.OPS_WORKFLOW in OpsPlanner.supported_task_types


def test_list_agent_cards_returns_one_per_registered_agent() -> None:
    cards = list_agent_cards()
    assert len(cards) == len(AGENT_REGISTRY)
    ids = {c.id for c in cards}
    assert ids == set(AGENT_REGISTRY)


def test_capability_input_schemas_are_json_schemas() -> None:
    """Every capability's input_schema should at least declare its top-level
    type — important for MCP tool serialization downstream."""
    for cls in AGENT_REGISTRY.values():
        for cap in cls.capabilities:
            assert "type" in cap.input_schema, (
                f"{cls.__name__}.capabilities[{cap.name}].input_schema missing top-level 'type'"
            )
            assert "type" in cap.output_schema, (
                f"{cls.__name__}.capabilities[{cap.name}].output_schema missing top-level 'type'"
            )

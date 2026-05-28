"""Coordinator routing tests.

Exercises the rule-based shortcuts (CUSTOMER_SUPPORT, OPS_WORKFLOW) which
don't require an LLM. The LLM-classification path for EMPLOYEE_QUESTION is
network-bound — covered by integration tests in Phase 10.
"""
from __future__ import annotations

import pytest

from agents.coordinator import LLM_DEFAULT_AGENT, RULE_BASED_ROUTING, CoordinatorAgent
from core.tasks import (
    CustomerSupportInput,
    OpsWorkflowInput,
    Task,
    TaskType,
)


@pytest.mark.asyncio
async def test_customer_support_routes_by_rule() -> None:
    agent = CoordinatorAgent()
    task = Task(
        type=TaskType.CUSTOMER_SUPPORT,
        input=CustomerSupportInput(
            ticket_subject="Login broken", ticket_body="Cannot sign in."
        ),
    )
    result = await agent.run(task)
    assert result.artifacts["routed_to"] == "customer_facing"
    assert "Rule-based" in result.summary


@pytest.mark.asyncio
async def test_ops_workflow_routes_by_rule() -> None:
    agent = CoordinatorAgent()
    task = Task(
        type=TaskType.OPS_WORKFLOW,
        input=OpsWorkflowInput(transcript="Lina: ship the migration."),
    )
    result = await agent.run(task)
    assert result.artifacts["routed_to"] == "ops_planner"


def test_rule_based_routing_table_is_complete_for_unambiguous_types() -> None:
    # CUSTOMER_SUPPORT and OPS_WORKFLOW must always have a rule-based default;
    # EMPLOYEE_QUESTION intentionally does NOT (it needs LLM classification).
    assert TaskType.CUSTOMER_SUPPORT in RULE_BASED_ROUTING
    assert TaskType.OPS_WORKFLOW in RULE_BASED_ROUTING
    assert TaskType.EMPLOYEE_QUESTION not in RULE_BASED_ROUTING


def test_llm_default_fallback_is_a_real_agent_id() -> None:
    """If the LLM hiccups, Coordinator falls back to LLM_DEFAULT_AGENT.
    That id must exist in the registry, or the pipeline fails harder than
    the original LLM error."""
    from agents import AGENT_REGISTRY

    assert LLM_DEFAULT_AGENT in AGENT_REGISTRY

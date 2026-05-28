"""Pollux agents package.

Public API:
    from agents import (
        BaseAgent,
        HRSpecialist, ITSpecialist, CustomerFacingSpecialist, OpsPlanner,
        CoordinatorAgent, EscalationAgent,
        AGENT_REGISTRY, get_agent, list_agent_cards,
        run_task,
    )
"""
from __future__ import annotations

from functools import lru_cache

from agents.base import BaseAgent
from agents.coordinator import CoordinatorAgent
from agents.customer_facing import CustomerFacingSpecialist
from agents.escalation import EscalationAgent
from agents.hr_specialist import HRSpecialist
from agents.it_specialist import ITSpecialist
from agents.ops_planner import OpsPlanner
from agents.pipeline import run_task
from core.tasks import AgentCard

# Single source of truth for the agent roster. Phase 4's pipeline + the
# Phase 6 MCP server + the Phase 7 A2A endpoints all read from here.
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    CoordinatorAgent.id: CoordinatorAgent,
    HRSpecialist.id: HRSpecialist,
    ITSpecialist.id: ITSpecialist,
    CustomerFacingSpecialist.id: CustomerFacingSpecialist,
    OpsPlanner.id: OpsPlanner,
    EscalationAgent.id: EscalationAgent,
}


@lru_cache(maxsize=None)
def get_agent(agent_id: str) -> BaseAgent:
    """Lazy singleton — one instance per agent class, built on first request.

    Instantiation triggers `BaseAgent.__init__()` which wires up the LLM,
    retriever (where applicable), and compiled LangGraph.
    """
    cls = AGENT_REGISTRY.get(agent_id)
    if cls is None:
        raise ValueError(
            f"Unknown agent: {agent_id!r}. "
            f"Available: {sorted(AGENT_REGISTRY)}"
        )
    return cls()


def list_agent_cards() -> list[AgentCard]:
    """Return every registered agent's discovery card. No instantiation —
    safe to call from anywhere without an HF_TOKEN."""
    return [cls.agent_card() for cls in AGENT_REGISTRY.values()]


__all__ = [
    "AGENT_REGISTRY",
    "BaseAgent",
    "CoordinatorAgent",
    "CustomerFacingSpecialist",
    "EscalationAgent",
    "HRSpecialist",
    "ITSpecialist",
    "OpsPlanner",
    "get_agent",
    "list_agent_cards",
    "run_task",
]

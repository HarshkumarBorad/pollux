"""System routes — health + agent discovery.

Public (no auth). Health is meant to be polled by load balancers / monitoring.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import async_sessionmaker

from agents import list_agent_cards
from api.dependencies import get_session_factory_dep
from api.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health(
    session_factory=Depends(get_session_factory_dep),
) -> HealthResponse:
    """Liveness probe. Confirms the DB is reachable + counts registered agents."""
    db_status = "connected"
    try:
        async with session_factory() as session:
            await session.execute_options()  # touches the session lazily
    except Exception:
        db_status = "unreachable"

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        db=db_status,
        agents=len(list_agent_cards()),
    )


@router.get("/agents", tags=["agents"])
async def list_agents() -> dict:
    """Return every registered agent's AgentCard.

    Same shape the A2A variant publishes at `.well-known/agent-card.json` —
    just aggregated into a single response."""
    cards = list_agent_cards()
    return {
        "count": len(cards),
        "agents": [card.model_dump(mode="json") for card in cards],
    }

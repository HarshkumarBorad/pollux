"""Pollux A2A server.

Mounts one A2A endpoint per Pollux agent on a single Starlette app, each
publishing its Agent Card at `/agents/<id>/.well-known/agent-card.json` and
accepting JSON-RPC tasks at `/agents/<id>/`.

Five public agents are exposed (Escalation is meta-only and intentionally
unmounted):
    /agents/hr_specialist
    /agents/it_specialist
    /agents/customer_facing
    /agents/ops_planner
    /agents/coordinator    ← runs the FULL pipeline via orchestrator + QA + persist

Run locally:
    python -m a2a_variant.server                    :: 127.0.0.1:8003
    python -m a2a_variant.server --port 9000
    python -m a2a_variant.server --host 0.0.0.0 --base-url https://pollux.example
"""
from __future__ import annotations

import argparse
import asyncio

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from agents import AGENT_REGISTRY
from core import telemetry
from core.db.migrate import create_all_tables

from a2a_variant.cards import build_card
from a2a_variant.executor import CoordinatorExecutor, PolluxAgentExecutor

# Escalation is a meta-agent (review-only); not a peer in the A2A sense.
SKIP_AGENTS: set[str] = {"escalation"}


def _build_executor(agent_id: str):
    """One executor per agent. Coordinator gets the pipeline-running variant;
    everyone else gets the generic specialist wrapper."""
    if agent_id == "coordinator":
        return CoordinatorExecutor()
    cls = AGENT_REGISTRY[agent_id]
    return PolluxAgentExecutor(cls())


def _build_agent_subapp(agent_card, executor) -> Starlette:
    """Wrap one agent's routes (Agent Card + JSON-RPC) in a Starlette sub-app
    so it can be mounted under `/agents/<id>` in the main app."""
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    # Agent Card is served at `<mount>/.well-known/agent-card.json`;
    # JSON-RPC dispatcher handles `<mount>/`.
    routes = (
        list(create_agent_card_routes(agent_card))
        + list(create_jsonrpc_routes(request_handler, rpc_url="/"))
    )
    return Starlette(routes=routes)


def build_app(base_url: str = "http://localhost:8003") -> Starlette:
    """Construct the Starlette ASGI app with all A2A endpoints mounted."""
    log = telemetry.get_logger("pollux.a2a.server")

    routes: list = []
    mounted_agents: list[dict] = []

    for agent_id, agent_cls in AGENT_REGISTRY.items():
        if agent_id in SKIP_AGENTS:
            continue

        card = build_card(agent_cls, base_url=base_url)
        executor = _build_executor(agent_id)
        sub_app = _build_agent_subapp(card, executor)

        mount_path = f"/agents/{agent_id}"
        routes.append(Mount(mount_path, app=sub_app))
        mounted_agents.append(
            {
                "id": agent_id,
                "name": agent_cls.name,
                "description": agent_cls.description,
                "url": f"{base_url}{mount_path}/",
                "card_url": f"{base_url}{mount_path}/.well-known/agent-card.json",
                "domain": agent_cls.domain.value if agent_cls.domain else None,
            }
        )
        log.info("a2a.mounted", agent_id=agent_id, path=mount_path)

    async def root(request):
        """Discovery endpoint — `GET /` lists every mounted agent."""
        return JSONResponse(
            {
                "name": "Pollux A2A Server",
                "description": (
                    "Pollux multi-agent system exposed via Google's Agent-to-Agent "
                    "protocol. Each agent is reachable at its own URL with an "
                    "Agent Card at /.well-known/agent-card.json. Same agent logic "
                    "as the MCP variant — only the transport differs."
                ),
                "agents": mounted_agents,
            }
        )

    routes.append(Route("/", endpoint=root))
    return Starlette(routes=routes)


def main() -> int:
    telemetry.init()

    parser = argparse.ArgumentParser(description="Pollux A2A server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "Externally-visible base URL — used inside Agent Cards. "
            "Defaults to http://<host>:<port>."
        ),
    )
    args = parser.parse_args()

    # Idempotent — guarantees the task store exists for the Coordinator
    # executor's orchestrator.submit() call.
    asyncio.run(create_all_tables())

    base_url = args.base_url or f"http://{args.host}:{args.port}"
    app = build_app(base_url=base_url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

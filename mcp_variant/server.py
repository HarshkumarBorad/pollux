"""Pollux MCP server.

Exposes the entire multi-agent system as MCP tools. The full Coordinator →
Specialist → Escalation pipeline (with persistence) is reachable as
`submit_*` tools; individual agents are reachable directly via `query_*` /
`draft_*` / `plan_*` tools; introspection lives in `list_agents` /
`list_tasks` / `get_task_status`.

The MCP server reuses the same compiled LangGraph agents and the same
SQLAlchemy task store that the orchestrator CLI (Phase 5), the upcoming
REST API (Phase 8), and the A2A variant (Phase 7) use. Switching between
inter-agent transports doesn't change the business logic.

Run over stdio (default — for Claude Desktop, Cline, Cursor, etc.):
    python -m mcp_variant.server

Run over Streamable HTTP for remote agents:
    python -m mcp_variant.server --transport http --port 8002

Run over SSE (legacy MCP HTTP transport):
    python -m mcp_variant.server --transport sse --port 8002
"""
from __future__ import annotations

import argparse
import asyncio

from fastmcp import FastMCP

from core import telemetry
from core.db.migrate import create_all_tables
from mcp_variant.tools import register_tools

INSTRUCTIONS = (
    "Pollux is a multi-agent system that automates three task domains: "
    "customer support (ticket → drafted reply), internal employee Q&A "
    "(HR + IT specialists), and operations workflow (meeting transcripts → "
    "action items). Use the `submit_*` tools to send a task through the "
    "full Coordinator → Specialist → Escalation pipeline (persisted to "
    "the task store with a queryable history). Use the direct `query_*` / "
    "`draft_*` / `plan_*` tools to invoke a single agent without "
    "persistence — faster but no audit trail. Call `list_agents` first "
    "if you're unsure which agent or submit tool fits, and "
    "`get_task_status` / `list_tasks` to inspect already-submitted work."
)

mcp = FastMCP(name="Pollux", instructions=INSTRUCTIONS)
register_tools(mcp)


_TRANSPORT_ALIASES = {
    "stdio": "stdio",
    "http": "streamable-http",  # the modern MCP HTTP transport
    "sse": "sse",                # legacy
}


def main() -> int:
    telemetry.init()
    parser = argparse.ArgumentParser(description="Pollux MCP server.")
    parser.add_argument(
        "--transport",
        choices=list(_TRANSPORT_ALIASES.keys()),
        default="stdio",
        help="Transport mode. Default 'stdio' — used by Claude Desktop, Cline, Cursor.",
    )
    parser.add_argument("--port", type=int, default=8002, help="Port for http / sse transport.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for http / sse transport.")
    args = parser.parse_args()

    # Idempotent — ensures the task store schema is present before the first
    # `submit_*` tool call. Cheap to run on every startup.
    asyncio.run(create_all_tables())

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(
            transport=_TRANSPORT_ALIASES[args.transport],
            host=args.host,
            port=args.port,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

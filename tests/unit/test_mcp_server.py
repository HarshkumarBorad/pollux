"""Smoke tests for the MCP server.

Confirms tool registration runs cleanly and every expected tool name shows
up on the FastMCP instance. Tool *invocation* needs HF / DB and is covered
by integration tests in Phase 10.
"""
from __future__ import annotations

import pytest

# The expected tools — keep this list in sync with mcp_variant/tools.py.
EXPECTED_TOOLS = {
    # submit_* (orchestrated + persisted)
    "submit_employee_question",
    "submit_customer_ticket",
    "submit_ops_workflow",
    # direct
    "query_hr",
    "query_it",
    "draft_customer_reply",
    "plan_from_meeting",
    # discovery / inspection
    "list_agents",
    "get_task_status",
    "list_tasks",
}


def test_mcp_module_imports_cleanly() -> None:
    """If any @mcp.tool registration fails (wrong arg types, typo in decorator
    options, etc.) the import crashes — and that's what this test catches."""
    from mcp_variant import server

    assert server.mcp is not None
    assert server.mcp.name == "Pollux"


@pytest.mark.asyncio
async def test_all_expected_tools_are_registered() -> None:
    """FastMCP exposes registered tools via `list_tools()` — confirm every
    name we promise in the docs is actually present."""
    from mcp_variant.server import mcp

    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    missing = EXPECTED_TOOLS - names
    assert not missing, f"Tools missing from MCP server registration: {missing}"

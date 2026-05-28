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


def _registered_tool_names(mcp_instance) -> set[str]:
    """Introspect registered FastMCP tools.

    FastMCP 2.x's public list-tools method has moved between minor versions
    (`list_tools`, `get_tools`, `_mcp_server.list_tools`, ...). The internal
    `_tool_manager._tools` dict is the actual storage and has stayed put
    across the 2.x series — every `@mcp.tool()` registration writes here.
    Worth the private-attribute access for test stability.
    """
    tm = getattr(mcp_instance, "_tool_manager", None)
    if tm is not None:
        for attr in ("_tools", "tools"):
            tools = getattr(tm, attr, None)
            if isinstance(tools, dict):
                return set(tools.keys())
    return set()


def test_mcp_module_imports_cleanly() -> None:
    """If any @mcp.tool registration fails (wrong arg types, typo in decorator
    options, etc.) the import crashes — that's what this test catches."""
    from mcp_variant import server

    assert server.mcp is not None
    assert server.mcp.name == "Pollux"


def test_all_expected_tools_are_registered() -> None:
    """Every name we promise in the README must be reachable as a tool."""
    from mcp_variant.server import mcp

    names = _registered_tool_names(mcp)
    assert names, (
        "Could not introspect FastMCP tools. Either FastMCP's internal layout "
        "changed (look at `mcp._tool_manager`) or registration failed silently."
    )
    missing = EXPECTED_TOOLS - names
    assert not missing, f"Tools missing from MCP server registration: {missing}"

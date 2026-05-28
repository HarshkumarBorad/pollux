"""Pollux MCP server variant.

Exposes the full Pollux multi-agent system as MCP tools. Same business
logic as the A2A variant (Phase 7) — only the inter-agent transport differs.

Entry point lives in `mcp_variant.server`; keep this `__init__` empty so
`python -m mcp_variant.server` doesn't trigger a "module found in sys.modules"
RuntimeWarning from runpy.
"""

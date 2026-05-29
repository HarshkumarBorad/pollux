"""Pollux A2A server variant.

Exposes the full Pollux agent roster via Google's Agent-to-Agent (A2A)
protocol — each agent has its own HTTP endpoint and Agent Card. Same agent
business logic as the MCP variant (Phase 6); only the inter-agent transport
differs.

Entry point lives in `a2a_variant.server`; keep this `__init__` empty so
`python -m a2a_variant.server` doesn't trigger a runpy RuntimeWarning.
"""

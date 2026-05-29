"""Pollux REST API.

The third client surface (alongside the MCP variant and A2A variant). This is
the protocol-agnostic, "for humans / web apps / external integrations"
front-end:

  - POST /tasks/{question,ticket,meeting} — task submission (sync or async)
  - GET  /tasks                           — recent tasks
  - GET  /tasks/{id}                      — current state + events
  - WS   /tasks/{id}/stream               — live event subscription
  - GET  /agents                          — agent discovery
  - GET  /health                          — liveness

Same agent business logic as every other surface — only the transport differs.

Entry point: `from api.main import app` (or `python -m api.server`).
"""

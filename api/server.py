"""CLI wrapper around `uvicorn` for the Pollux REST API.

Equivalent to running `uvicorn api.main:app` directly — but exposes the
same flag style as the other variants (`mcp_variant.server`,
`a2a_variant.server`, `orchestrator.cli`) so a fresh clone has one
muscle memory.
"""
from __future__ import annotations

import argparse

import uvicorn


def main() -> int:
    parser = argparse.ArgumentParser(description="Pollux REST API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--reload", action="store_true", help="Hot-reload on source changes (dev only)."
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
    )
    args = parser.parse_args()

    # The reload-capable spawn requires uvicorn to import the app, so it
    # always receives the module-string form.
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

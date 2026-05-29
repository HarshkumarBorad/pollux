"""FastAPI application factory + module-level `app` for uvicorn.

Auto-generated OpenAPI / Swagger UI lives at:
    GET /docs       — interactive Swagger UI
    GET /redoc      — ReDoc
    GET /openapi.json

Run locally:
    python -m api.server                    :: 127.0.0.1:8001
    python -m api.server --reload           :: hot-reload during dev
    python -m api.server --host 0.0.0.0     :: bind all interfaces
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import system, tasks, websocket
from core import telemetry
from core.db.migrate import create_all_tables

API_TITLE = "Pollux REST API"
API_VERSION = "0.8.0"
API_DESCRIPTION = (
    "Protocol-agnostic HTTP interface to the Pollux multi-agent system. "
    "Submit a task (employee question, customer ticket, or meeting transcript), "
    "poll for results, or subscribe to live progress via the WebSocket. "
    "Same agent business logic as the MCP and A2A variants — only the transport "
    "differs."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks. Idempotently runs DB migrations on boot
    so a fresh clone works with a single `python -m api.server`."""
    telemetry.init()
    await create_all_tables()
    yield


def build_app() -> FastAPI:
    """Construct a fresh FastAPI app — used by tests to inject fixtures via
    `app.dependency_overrides`. Production uses the module-level `app`
    instead so uvicorn's `--reload` can find it."""
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
    )

    # Permissive CORS for local dev / the Phase 9 Streamlit UI. Tighten for
    # any externally-exposed deploy.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(tasks.router)
    app.include_router(websocket.router)

    return app


# Module-level app for `uvicorn api.main:app --reload`.
app = build_app()

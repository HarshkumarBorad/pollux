"""FastAPI dependencies for the REST API.

`get_orchestrator` and `get_session_factory_dep` are kept as separate
dependency callables so tests can override them with
`app.dependency_overrides[...]` to inject in-memory orchestrators / DBs.

`require_api_key` enforces auth IF `POLLUX_API_KEY` is set in env. If
unset, the API is open — useful for local dev. Production sets the env
var and clients pass it in `X-API-Key`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import PolluxConfig, get_config
from core.db.session import get_session_factory
from orchestrator import TaskOrchestrator


def get_orchestrator() -> TaskOrchestrator:
    """Default orchestrator — uses the process-wide DB session factory.

    Tests override this with `app.dependency_overrides[get_orchestrator]`.
    """
    return TaskOrchestrator()


def get_session_factory_dep() -> async_sessionmaker[AsyncSession]:
    """The session factory used by routes that need raw repository access
    (event listing, etc.). Same override pattern as `get_orchestrator`."""
    return get_session_factory()


async def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> None:
    """API-key auth. No-op if `POLLUX_API_KEY` isn't set.

    Header name is conventional (`X-API-Key`). When auth is enabled, missing
    or wrong key returns 401.
    """
    config = get_config()
    expected = (config.pollux_api_key or "").strip()
    if not expected:
        return  # Auth disabled.
    if not x_api_key or x_api_key.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key header.",
        )

"""Async SQLAlchemy session management.

Single engine + session factory per process. Both are cached behind module-
level singletons; tests override them by calling `reset_engine()` between
runs (e.g. to swap in `sqlite+aiosqlite:///:memory:`).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_config

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """Process-wide async SQLAlchemy engine. Reads `database_url` from PolluxConfig.

    The default `sqlite+aiosqlite:///pollux.db` works with no extra setup;
    swap to `postgresql+asyncpg://...` in production by setting DATABASE_URL.
    """
    global _engine
    if _engine is None:
        config = get_config()
        _engine = create_async_engine(
            config.database_url,
            echo=False,
            future=True,
            # SQLite needs check_same_thread off; aiosqlite handles that
            # itself, but pass an empty connect_args to silence the warning.
            connect_args={} if not config.database_url.startswith("sqlite") else {},
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Factory used by the repository layer. Sessions are expire_on_commit=False
    so callers can keep using returned ORM rows after a commit."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


def reset_engine() -> None:
    """Drop the cached engine + session factory. Tests call this between
    runs so the in-memory `sqlite:///:memory:` database doesn't bleed."""
    global _engine, _session_factory
    if _engine is not None:
        # Don't await dispose() here — engine.dispose() is sync-safe to skip
        # in test setup. Production should explicitly `await engine.dispose()`
        # on shutdown.
        _engine = None
    _session_factory = None

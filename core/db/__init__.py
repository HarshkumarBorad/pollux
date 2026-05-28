"""Pollux database layer — async SQLAlchemy 2.0 over aiosqlite (default).

Public API:
    from core.db import (
        Base,
        TaskRecord, TaskEventRecord,
        get_engine, get_session_factory, reset_engine,
        create_all_tables, drop_all_tables, reset_all_tables,
    )
"""
from core.db.migrate import create_all_tables, drop_all_tables, reset_all_tables
from core.db.models import Base, TaskEventRecord, TaskRecord
from core.db.session import get_engine, get_session_factory, reset_engine

__all__ = [
    "Base",
    "TaskRecord",
    "TaskEventRecord",
    "get_engine",
    "get_session_factory",
    "reset_engine",
    "create_all_tables",
    "drop_all_tables",
    "reset_all_tables",
]

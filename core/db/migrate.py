"""Schema creation / drop.

No Alembic in Phase 5 — `create_all()` is enough for SQLite during local
development and the portfolio demo. Phase 10 may add Alembic migrations
when the schema starts evolving.

Run from CLI:
    python -m core.db.migrate create
    python -m core.db.migrate drop      # destructive — wipes all task data
    python -m core.db.migrate reset     # drop + create
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from core import telemetry
from core.db.models import Base
from core.db.session import get_engine


async def create_all_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def reset_all_tables() -> None:
    await drop_all_tables()
    await create_all_tables()


async def _main(args) -> int:
    log = telemetry.get_logger("pollux.db.migrate")
    actions = {
        "create": create_all_tables,
        "drop": drop_all_tables,
        "reset": reset_all_tables,
    }
    action = actions[args.action]
    log.info("db.migrate_start", action=args.action)
    await action()
    log.info("db.migrate_done", action=args.action)
    print(f"Done: {args.action}")
    return 0


def main() -> int:
    telemetry.init()
    parser = argparse.ArgumentParser(description="Pollux DB schema management.")
    parser.add_argument("action", choices=["create", "drop", "reset"])
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())

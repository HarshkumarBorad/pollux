"""Bulk-ingest the bundled sample knowledge docs into all four namespaces.

Run after `python -m core.db.migrate create`. Idempotent — re-running just
upserts unchanged chunks.

Usage:
    python scripts/ingest_samples.py
    python scripts/ingest_samples.py --reset    :: wipe each domain first
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make the project root importable regardless of how this script is invoked.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import telemetry  # noqa: E402
from core.knowledge import KnowledgeDomain, ingest_directory  # noqa: E402

DOCS_ROOT = ROOT / "data" / "knowledge"
SUPPORTED_EXTS = {".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm"}


def _has_ingestible_files(path: Path) -> bool:
    return any(
        p.is_file() and p.suffix.lower() in SUPPORTED_EXTS for p in path.rglob("*")
    )


async def _main(args) -> int:
    telemetry.init()
    log = telemetry.get_logger("pollux.scripts.ingest_samples")

    if not DOCS_ROOT.is_dir():
        print(f"ERROR: docs root {DOCS_ROOT} does not exist", file=sys.stderr)
        return 1

    grand_total = 0
    for domain in KnowledgeDomain:
        path = DOCS_ROOT / domain.value
        if not path.is_dir():
            print(f"  [skip] {domain.value}: {path} does not exist")
            continue
        if not _has_ingestible_files(path):
            print(f"  [skip] {domain.value}: no supported files in {path}")
            continue
        log.info("ingest.start", domain=domain.value, path=str(path))
        count = await ingest_directory(path, domain, reset_domain=args.reset)
        grand_total += count
        print(f"  [ok]   {domain.value}: {count} chunks ingested from {path}")

    print(f"\nDone. Total chunks ingested across all domains: {grand_total}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest bundled sample knowledge docs.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe each domain before ingesting. Useful for clean re-runs.",
    )
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())

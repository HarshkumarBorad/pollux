"""Knowledge-layer CLI — ingest documents, run test queries, manage domains.

Subcommands:
    ingest   --domain <d> --path <p> [--reset]
    query    "question"   [--domain <d>] [--top-k N]
    count
    reset    --domain <d>

Usage examples:
    python -m core.knowledge.cli ingest --domain hr --path ./data/knowledge/hr
    python -m core.knowledge.cli query "What is the leave policy?" --domain hr
    python -m core.knowledge.cli count
    python -m core.knowledge.cli reset --domain hr
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from core import telemetry
from core.knowledge.client import get_collection
from core.knowledge.domains import KnowledgeDomain
from core.knowledge.ingest import count_by_domain, ingest_directory
from core.knowledge.retriever import Retriever


async def cmd_ingest(args) -> int:
    path = Path(args.path)
    domain = KnowledgeDomain(args.domain)
    count = await ingest_directory(path, domain, reset_domain=args.reset)
    print(f"\nDone. Added {count} chunk(s) to domain '{domain.value}'.")
    return 0


async def cmd_query(args) -> int:
    domain = KnowledgeDomain(args.domain) if args.domain else None
    retriever = Retriever()
    chunks = await retriever.retrieve(args.question, domain=domain, top_k=args.top_k)
    print(f"\nRetrieved {len(chunks)} chunk(s):\n")
    for c in chunks:
        loc = c.filename or c.source
        if c.page >= 0:
            loc += f" (page {c.page + 1})"
        domain_tag = f" [{c.domain}]" if c.domain else ""
        print(f"--- [{c.rank}]{domain_tag} {loc}  (distance={c.distance:.3f}) ---")
        preview = c.text if len(c.text) <= 500 else c.text[:500] + " ..."
        print(preview)
        print()
    return 0


async def cmd_count(args) -> int:
    counts = await asyncio.to_thread(count_by_domain)
    print("Chunks per domain:")
    for domain, count in counts.items():
        print(f"  {domain:<10} {count}")
    print(f"  {'total':<10} {sum(counts.values())}")
    return 0


async def cmd_reset(args) -> int:
    domain = KnowledgeDomain(args.domain)
    collection = get_collection()
    await asyncio.to_thread(collection.delete, where={"domain": domain.value})
    print(f"Reset domain '{domain.value}'.")
    return 0


def main() -> int:
    telemetry.init()

    parser = argparse.ArgumentParser(description="Pollux knowledge layer CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest a directory into a domain.")
    p_ingest.add_argument(
        "--domain", required=True, choices=[d.value for d in KnowledgeDomain]
    )
    p_ingest.add_argument("--path", required=True)
    p_ingest.add_argument(
        "--reset", action="store_true", help="Wipe the domain before ingest."
    )

    p_query = sub.add_parser("query", help="Run a test query against the collection.")
    p_query.add_argument("question")
    p_query.add_argument(
        "--domain",
        choices=[d.value for d in KnowledgeDomain],
        default=None,
        help="Filter retrieval to a single domain. Omit to search all.",
    )
    p_query.add_argument("--top-k", type=int, default=5)

    sub.add_parser("count", help="Show chunk counts per domain.")

    p_reset = sub.add_parser("reset", help="Wipe a domain.")
    p_reset.add_argument(
        "--domain", required=True, choices=[d.value for d in KnowledgeDomain]
    )

    args = parser.parse_args()

    handlers = {
        "ingest": cmd_ingest,
        "query": cmd_query,
        "count": cmd_count,
        "reset": cmd_reset,
    }
    return asyncio.run(handlers[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())

"""Async ingest pipeline.

Walks a directory, loads files, chunks them, embeds via HF, upserts into the
shared ChromaDB collection with domain-tagged metadata.

Content-hashed IDs make re-ingestion idempotent — re-running on the same
files overwrites in place rather than duplicating. Renamed files produce
new IDs (orphan rows for the old name); a proper "delete-by-filename"
helper can land in Phase 10 if it ever matters.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from core.knowledge.chunker import get_chunker
from core.knowledge.client import get_collection
from core.knowledge.domains import KnowledgeDomain
from core.knowledge.embedder import get_embedder
from core.knowledge.loaders import load_directory
from core.telemetry import get_logger

log = get_logger("pollux.knowledge.ingest")

# ChromaDB only persists primitive metadata.
CHROMA_METADATA_PRIMITIVES = (str, int, float, bool)


def _stable_id(text: str, source: str, index: int) -> str:
    digest = hashlib.sha256(f"{source}::{index}::{text}".encode("utf-8")).hexdigest()
    return digest[:24]


def _flatten_metadata(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if isinstance(v, CHROMA_METADATA_PRIMITIVES)}


async def ingest_directory(
    path: Path | str,
    domain: KnowledgeDomain,
    reset_domain: bool = False,
) -> int:
    """Ingest every supported file under `path` into the shared collection,
    tagging each chunk with the given domain.

    `reset_domain=True` wipes all existing chunks for this domain before
    ingest. Other domains are untouched — useful when re-ingesting a
    specific area without re-doing the others.
    """
    path = Path(path)
    collection = get_collection()
    embedder = get_embedder()

    if reset_domain:
        log.info("knowledge.reset_domain", domain=domain.value)
        await asyncio.to_thread(
            collection.delete, where={"domain": domain.value}
        )

    log.info("knowledge.load", path=str(path), domain=domain.value)
    docs: List[Document] = await asyncio.to_thread(load_directory, path)
    if not docs:
        log.warning("knowledge.no_docs", path=str(path))
        return 0
    log.info("knowledge.loaded", document_count=len(docs), domain=domain.value)

    chunker = get_chunker()
    chunks = chunker.split_documents(docs)
    log.info("knowledge.chunked", chunk_count=len(chunks), domain=domain.value)

    # Tag every chunk with its origin domain.
    for c in chunks:
        c.metadata["domain"] = domain.value

    texts = [c.page_content for c in chunks]
    log.info(
        "knowledge.embed_start",
        chunk_count=len(chunks),
        model=embedder.config.hf_embed_model,
    )
    embeddings = await embedder.aembed(texts)

    ids = [
        _stable_id(c.page_content, c.metadata.get("source", ""), i)
        for i, c in enumerate(chunks)
    ]
    metadatas = [_flatten_metadata(c.metadata) for c in chunks]

    log.info("knowledge.upsert", chunk_count=len(chunks), domain=domain.value)
    await asyncio.to_thread(
        collection.upsert,
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    total = await asyncio.to_thread(collection.count)
    log.info(
        "knowledge.ingest_done",
        chunks_added=len(chunks),
        collection_total=total,
        domain=domain.value,
    )
    return len(chunks)


def count_by_domain() -> dict[str, int]:
    """Return `{domain_value: chunk_count}` across the collection.

    Synchronous because ChromaDB's `get(...)` doesn't accept an embedding
    and is fast — wrapping in asyncio adds noise without benefit.
    """
    collection = get_collection()
    counts: dict[str, int] = {}
    for domain in KnowledgeDomain:
        result = collection.get(where={"domain": domain.value}, include=[])
        counts[domain.value] = len(result.get("ids", []))
    return counts

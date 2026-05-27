"""Async retriever — domain-filterable semantic search.

The retriever is what every specialist agent calls in Phase 3+. It always
returns `RetrievedChunk` (a pydantic model) rather than raw Chroma dicts,
so downstream code doesn't depend on Chroma's internal response shape.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from pydantic import BaseModel

from core.knowledge.client import get_collection
from core.knowledge.domains import KnowledgeDomain
from core.knowledge.embedder import get_embedder
from core.telemetry import get_logger

log = get_logger("pollux.knowledge.retrieve")

NO_PAGE = -1  # sentinel: chunk doesn't come from a paginated source (md / txt / html)


class RetrievedChunk(BaseModel):
    """One retrieval hit, ready to be cited in an agent's response."""

    rank: int                # 1-based, monotonic in result order
    text: str
    source: str = ""         # absolute path to source file
    filename: str = ""       # basename of source file, for citations
    page: int = NO_PAGE      # 0-indexed page number; NO_PAGE for non-paginated formats
    domain: str = ""         # KnowledgeDomain value
    distance: float = 0.0    # cosine distance — lower is better


def _extract_page(meta: dict) -> int:
    page = meta.get("page")
    if page is None:
        return NO_PAGE
    try:
        return int(page)
    except (TypeError, ValueError):
        return NO_PAGE


class Retriever:
    """Stateless wrapper around the shared collection. Cheap to construct
    — singletons are unnecessary."""

    def __init__(self) -> None:
        self.collection = get_collection()
        self.embedder = get_embedder()

    async def retrieve(
        self,
        query: str,
        domain: Optional[KnowledgeDomain] = None,
        top_k: int = 5,
    ) -> List[RetrievedChunk]:
        """Embed the query, search the collection (optionally filtered to one
        domain via the `domain` metadata field), return top-k chunks."""
        query_embedding = await self.embedder.aembed_query(query)

        where = {"domain": domain.value} if domain else None

        result = await asyncio.to_thread(
            self.collection.query,
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        documents = result["documents"][0] if result["documents"] else []
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []

        chunks: List[RetrievedChunk] = []
        for i, (doc, meta, dist) in enumerate(
            zip(documents, metadatas, distances), start=1
        ):
            meta = meta or {}
            chunks.append(
                RetrievedChunk(
                    rank=i,
                    text=doc,
                    source=str(meta.get("source", "")),
                    filename=str(meta.get("filename", "")),
                    page=_extract_page(meta),
                    domain=str(meta.get("domain", "")),
                    distance=float(dist),
                )
            )

        log.info(
            "retrieved",
            query_preview=query[:80],
            domain=domain.value if domain else "all",
            chunk_count=len(chunks),
            top_distance=chunks[0].distance if chunks else None,
        )
        return chunks

"""Pollux knowledge layer — standalone retrieval over a single shared
ChromaDB collection with per-chunk domain metadata for filtering.

Public API:
    from core.knowledge import (
        KnowledgeDomain,
        Retriever, RetrievedChunk,
        ingest_directory, count_by_domain,
        get_collection, get_embedder,
    )
"""
from core.knowledge.client import get_client, get_collection
from core.knowledge.domains import KnowledgeDomain
from core.knowledge.embedder import HFInferenceEmbedder, get_embedder
from core.knowledge.ingest import count_by_domain, ingest_directory
from core.knowledge.retriever import RetrievedChunk, Retriever

__all__ = [
    "KnowledgeDomain",
    "HFInferenceEmbedder",
    "RetrievedChunk",
    "Retriever",
    "count_by_domain",
    "get_client",
    "get_collection",
    "get_embedder",
    "ingest_directory",
]

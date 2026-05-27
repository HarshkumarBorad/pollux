"""Unit tests for the chunker.

The chunker is the only Phase 2 component we can unit-test without a network
round-trip (ingest and retrieve need HF + ChromaDB; those go to integration
tests in Phase 10).
"""
from __future__ import annotations

from langchain_core.documents import Document

from core.knowledge.chunker import get_chunker


def test_chunker_respects_chunk_size() -> None:
    chunker = get_chunker(chunk_size=100, chunk_overlap=20)
    doc = Document(page_content="A" * 500, metadata={"source": "test.txt"})
    chunks = chunker.split_documents([doc])
    assert chunks, "expected at least one chunk"
    assert all(len(c.page_content) <= 100 for c in chunks)


def test_chunker_preserves_per_doc_metadata() -> None:
    chunker = get_chunker(chunk_size=50, chunk_overlap=10)
    doc = Document(
        page_content="x " * 200,
        metadata={"source": "a.txt", "filename": "a.txt", "page": 0},
    )
    chunks = chunker.split_documents([doc])
    for c in chunks:
        assert c.metadata["source"] == "a.txt"
        assert c.metadata["filename"] == "a.txt"
        assert c.metadata["page"] == 0


def test_chunker_handles_multiple_docs() -> None:
    chunker = get_chunker(chunk_size=80, chunk_overlap=10)
    docs = [
        Document(page_content="paragraph one " * 30, metadata={"source": "1.md"}),
        Document(page_content="paragraph two " * 30, metadata={"source": "2.md"}),
    ]
    chunks = chunker.split_documents(docs)
    sources = {c.metadata["source"] for c in chunks}
    assert sources == {"1.md", "2.md"}


def test_chunker_short_document_passes_through() -> None:
    chunker = get_chunker(chunk_size=500, chunk_overlap=50)
    doc = Document(page_content="short", metadata={"source": "tiny.txt"})
    chunks = chunker.split_documents([doc])
    assert len(chunks) == 1
    assert chunks[0].page_content == "short"

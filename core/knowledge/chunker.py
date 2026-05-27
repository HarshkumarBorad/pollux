"""Text chunker.

Single strategy: recursive character splitter. Pollux doesn't use semantic
chunking (cost / latency not worth it for the document types we handle).
Stays fast, deterministic, and the same across all four knowledge domains.
"""
from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter


def get_chunker(
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

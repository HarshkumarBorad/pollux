"""Tests for the citation extraction and JSON parsing utilities.

These run without any network call — pure logic over pydantic objects."""
from __future__ import annotations

import pytest

from agents.utils import (
    extract_citations,
    format_sources,
    parse_json_response,
)
from core.knowledge import RetrievedChunk


def _chunk(rank: int, text: str, **kw) -> RetrievedChunk:
    return RetrievedChunk(rank=rank, text=text, **kw)


# ----- format_sources -----------------------------------------------------

def test_format_sources_empty() -> None:
    assert format_sources([]) == "(no sources)"


def test_format_sources_includes_page_when_set() -> None:
    chunks = [_chunk(1, "lorem", filename="a.pdf", page=4)]
    out = format_sources(chunks)
    assert "[1]" in out
    # Page is displayed 1-indexed (page 4 stored → page 5 shown).
    assert "page 5" in out


def test_format_sources_omits_page_for_non_paginated() -> None:
    chunks = [_chunk(1, "lorem", filename="a.md", page=-1)]
    out = format_sources(chunks)
    assert "page" not in out.lower()


# ----- extract_citations --------------------------------------------------

def test_extract_citations_basic() -> None:
    chunks = [
        _chunk(1, "X", filename="a.md", domain="hr"),
        _chunk(2, "Y", filename="b.md", domain="hr"),
    ]
    answer = "Foo [1] and bar [2]."
    citations = extract_citations(answer, chunks)
    assert [c.source for c in citations] == [
        chunks[0].filename if chunks[0].source == "" else chunks[0].source,
        chunks[1].filename if chunks[1].source == "" else chunks[1].source,
    ]


def test_extract_citations_dedupes_preserving_order() -> None:
    chunks = [_chunk(i, "x", filename=f"{i}.md") for i in range(1, 4)]
    answer = "alpha [2] beta [1] gamma [2] delta [3]"
    citations = extract_citations(answer, chunks)
    # First appearance order: 2, 1, 3
    assert [c.source for c in citations] == ["2.md", "1.md", "3.md"]


def test_extract_citations_drops_hallucinated_markers() -> None:
    chunks = [_chunk(1, "x", filename="real.md")]
    answer = "Real [1] plus fake [7] and fake [42]."
    citations = extract_citations(answer, chunks)
    assert len(citations) == 1
    assert citations[0].source == "real.md"


def test_extract_citations_distance_to_score() -> None:
    chunks = [_chunk(1, "x", filename="a.md", distance=0.0)]
    assert extract_citations("hit [1]", chunks)[0].score == pytest.approx(1.0)
    chunks = [_chunk(1, "x", filename="a.md", distance=2.0)]
    assert extract_citations("hit [1]", chunks)[0].score == pytest.approx(0.0)


# ----- parse_json_response ------------------------------------------------

def test_parse_json_direct() -> None:
    out = parse_json_response('{"a": 1, "b": [2, 3]}')
    assert out == {"a": 1, "b": [2, 3]}


def test_parse_json_with_markdown_fences() -> None:
    text = """```json
{"subtasks": [{"task": "ship it"}]}
```"""
    out = parse_json_response(text)
    assert out == {"subtasks": [{"task": "ship it"}]}


def test_parse_json_with_prose_prefix() -> None:
    text = """Sure, here is the JSON you requested:
{"x": 1}"""
    out = parse_json_response(text)
    assert out == {"x": 1}


def test_parse_json_returns_default_on_unparseable() -> None:
    assert parse_json_response("nope, not JSON at all", default={"x": 0}) == {"x": 0}
    assert parse_json_response("") is None


def test_parse_json_array_at_top_level() -> None:
    assert parse_json_response("[1, 2, 3]") == [1, 2, 3]

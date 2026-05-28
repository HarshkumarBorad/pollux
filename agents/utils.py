"""Utility functions shared by every agent.

Kept dependency-free so that unit tests can exercise them without
instantiating LLM clients or ChromaDB.
"""
from __future__ import annotations

import json
import re
from typing import Any

from core.knowledge import RetrievedChunk
from core.tasks import Citation

# Matches inline `[1]`, `[2]`, `[42]` citation markers.
CITE_PATTERN = re.compile(r"\[(\d+)\]")


def format_sources(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as a numbered SOURCES block for LLM prompts.

    The numbers are what the LLM uses as `[N]` inline citations; matching them
    back to chunks happens in `extract_citations()`.
    """
    if not chunks:
        return "(no sources)"
    lines: list[str] = []
    for c in chunks:
        loc = c.filename or "source"
        if c.page >= 0:
            loc = f"{loc} (page {c.page + 1})"
        lines.append(f"[{c.rank}] {loc}:\n{c.text}")
    return "\n\n".join(lines)


def extract_citations(
    answer_text: str, chunks: list[RetrievedChunk]
) -> list[Citation]:
    """Scan an LLM answer for `[N]` markers and build the matching Citation list.

    Order = order of first appearance, deduped. Hallucinated citation numbers
    (e.g. LLM cites `[7]` when only 5 chunks were given) are silently dropped.
    """
    seen: set[int] = set()
    cited_ranks: list[int] = []
    for match in CITE_PATTERN.finditer(answer_text):
        try:
            n = int(match.group(1))
        except ValueError:
            continue
        if n not in seen:
            seen.add(n)
            cited_ranks.append(n)

    rank_map = {c.rank: c for c in chunks}
    citations: list[Citation] = []
    for n in cited_ranks:
        chunk = rank_map.get(n)
        if chunk is None:
            continue
        # Cosine distance is in [0, 2]; map to a [0, 1] similarity for display.
        similarity = max(0.0, 1.0 - chunk.distance / 2.0)
        citations.append(
            Citation(
                source=chunk.source or chunk.filename or "unknown",
                text=chunk.text,
                score=similarity,
                domain=chunk.domain or None,
            )
        )
    return citations


def parse_json_response(text: str, default: Any = None) -> Any:
    """Parse a JSON object/array from an LLM response.

    LLMs frequently wrap JSON in markdown code fences despite being told not
    to, or prepend prose. This tries (in order): direct parse, fence-stripped
    parse, then a regex grab of the first balanced-looking JSON object.
    """
    text = text.strip()

    # 1. Strip ```json ... ``` or ``` ... ``` fences if present.
    if text.startswith("```"):
        stripped = re.sub(r"^```(?:json|JSON)?\s*\n?", "", text)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # 2. Direct parse.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Find the first `{...}` or `[...]` in the text. Greedy match — works
    #    for the simple JSON shapes our planner prompt requests; would need
    #    a real bracket-counting parser for arbitrarily nested input.
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue

    return default

"""Knowledge domain taxonomy.

Pollux's specialist agents are scoped to a specific domain — HR docs for the
HR agent, IT docs for the Tech agent, product docs for the Customer-Facing
agent. The Ops Planner and Coordinator don't bind to a domain; they read
across the collection or filter dynamically.

All chunks ingested into the shared ChromaDB collection are tagged with a
`domain` metadata key; the retriever passes `where={"domain": "<x>"}` to
ChromaDB to slice cleanly at query time. This is the leaner alternative to
DocuMind's multi-collection setup — same isolation guarantees, less moving
parts.
"""
from __future__ import annotations

from enum import Enum


class KnowledgeDomain(str, Enum):
    HR = "hr"
    IT = "it"
    PRODUCT = "product"
    GENERAL = "general"  # cross-domain / uncategorized

    @property
    def description(self) -> str:
        return _DESCRIPTIONS[self]


_DESCRIPTIONS: dict[KnowledgeDomain, str] = {
    KnowledgeDomain.HR: "HR policies, onboarding, leave, code of conduct",
    KnowledgeDomain.IT: "Technical documentation, API references, SDK guides, ADRs",
    KnowledgeDomain.PRODUCT: "Product manuals, release notes, customer FAQ",
    KnowledgeDomain.GENERAL: "Cross-domain or general organizational knowledge",
}

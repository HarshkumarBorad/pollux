"""Customer-Facing Specialist.

Two-stage pipeline:

  retrieve  → draft (internal-tone, with [N] citations for QA)
            → rewrite (external-tone, citations stripped)

The two-stage split is deliberate. The internal draft remains in the
TaskResult.artifacts for QA / audit, while the customer-facing reply is the
summary. Decoupling tone from facts makes each stage easier to test, debug,
and tune independently in later phases.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import BaseAgent
from agents.prompts import CUSTOMER_FACING_DRAFT, CUSTOMER_FACING_REWRITE
from agents.utils import extract_citations, format_sources
from core.knowledge import KnowledgeDomain, RetrievedChunk
from core.tasks import (
    Capability,
    Citation,
    CustomerSupportInput,
    Task,
    TaskResult,
    TaskType,
)


class _CustomerFacingState(TypedDict, total=False):
    ticket_subject: str
    ticket_body: str
    retrieved: list[RetrievedChunk]
    internal_draft: str
    final_reply: str
    citations: list[Citation]


class CustomerFacingSpecialist(BaseAgent):
    id = "customer_facing"
    name = "Customer-Facing Specialist"
    description = (
        "Drafts external-facing replies to customer support tickets, with a "
        "factual internal draft and a customer-friendly rewrite."
    )
    capabilities = [
        Capability(
            name="draft_customer_reply",
            description="Draft a customer-facing reply for an incoming support ticket.",
            input_schema={
                "type": "object",
                "required": ["ticket_subject", "ticket_body"],
                "properties": {
                    "ticket_subject": {"type": "string"},
                    "ticket_body": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "final_reply": {"type": "string"},
                    "internal_draft": {"type": "string"},
                    "citations": {"type": "array"},
                },
            },
        )
    ]
    supported_task_types = [TaskType.CUSTOMER_SUPPORT]
    domain = KnowledgeDomain.PRODUCT
    # Slightly higher temperature on the rewrite produces more natural prose.
    llm_temperature = 0.3

    def _build_graph(self):
        async def retrieve_node(state: _CustomerFacingState) -> _CustomerFacingState:
            assert self.retriever is not None
            query = f"{state['ticket_subject']}\n{state['ticket_body']}"
            chunks = await self.retriever.retrieve(
                query, domain=self.domain, top_k=5
            )
            self.log.info("cf.retrieved", chunk_count=len(chunks))
            return {"retrieved": chunks}

        async def draft_node(state: _CustomerFacingState) -> _CustomerFacingState:
            retrieved = state.get("retrieved", [])
            sources_block = format_sources(retrieved)
            messages = [
                {"role": "system", "content": CUSTOMER_FACING_DRAFT},
                {
                    "role": "user",
                    "content": (
                        f"SOURCES:\n{sources_block}\n\n"
                        f"TICKET SUBJECT: {state['ticket_subject']}\n"
                        f"TICKET BODY: {state['ticket_body']}"
                    ),
                },
            ]
            draft = await self.llm.chat(messages, temperature=0.2)
            citations = extract_citations(draft, retrieved)
            self.log.info(
                "cf.drafted", chars=len(draft), citation_count=len(citations)
            )
            return {"internal_draft": draft, "citations": citations}

        async def rewrite_node(state: _CustomerFacingState) -> _CustomerFacingState:
            messages = [
                {"role": "system", "content": CUSTOMER_FACING_REWRITE},
                {
                    "role": "user",
                    "content": (
                        f"INTERNAL DRAFT:\n{state['internal_draft']}\n\n"
                        f"ORIGINAL TICKET:\nSubject: {state['ticket_subject']}\n"
                        f"Body: {state['ticket_body']}"
                    ),
                },
            ]
            final = await self.llm.chat(messages, max_tokens=700, temperature=0.4)
            self.log.info("cf.rewritten", chars=len(final))
            return {"final_reply": final}

        builder = StateGraph(_CustomerFacingState)
        builder.add_node("retrieve", retrieve_node)
        builder.add_node("draft", draft_node)
        builder.add_node("rewrite", rewrite_node)
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "draft")
        builder.add_edge("draft", "rewrite")
        builder.add_edge("rewrite", END)
        return builder.compile()

    async def run(self, task: Task) -> TaskResult:
        assert isinstance(task.input, CustomerSupportInput), (
            f"CustomerFacingSpecialist expects CustomerSupportInput; "
            f"got {type(task.input).__name__}"
        )
        self.log.info("cf.run_start", task_id=str(task.id))
        result = await self._graph.ainvoke(
            {
                "ticket_subject": task.input.ticket_subject,
                "ticket_body": task.input.ticket_body,
            }
        )
        final_reply = result.get("final_reply", "")
        internal_draft = result.get("internal_draft", "")
        citations = result.get("citations", [])
        # Confidence: how grounded was the draft (citation count) — proxy for
        # how reliably the rewrite stage will preserve the facts.
        confidence = min(1.0, 0.4 + 0.15 * len(citations))
        self.log.info(
            "cf.run_done",
            task_id=str(task.id),
            citations=len(citations),
            confidence=confidence,
        )
        return TaskResult(
            summary=final_reply,
            artifacts={
                "draft_reply": final_reply,  # Slot the support tool can paste straight into.
                "internal_draft": internal_draft,
            },
            citations=citations,
            confidence=confidence,
        )

"""IT/Tech Specialist.

Mirror of HRSpecialist with an IT-domain knowledge slice and a precision-
focused system prompt. Two near-duplicate agents is intentional — keeping
them separate makes the per-agent logging + tracing in Phase 10 clean, and
phases 6/7 expose them as separate MCP tools / A2A endpoints.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import BaseAgent
from agents.prompts import IT_SYSTEM
from agents.utils import extract_citations, format_sources
from core.knowledge import KnowledgeDomain, RetrievedChunk
from core.tasks import (
    Capability,
    Citation,
    EmployeeQuestionInput,
    Task,
    TaskResult,
    TaskType,
)

NO_INFO_MARKER = "I don't have enough information in our technical docs"


class _ITState(TypedDict, total=False):
    question: str
    retrieved: list[RetrievedChunk]
    answer: str
    citations: list[Citation]


class ITSpecialist(BaseAgent):
    id = "it_specialist"
    name = "IT/Tech Specialist"
    description = "Answers IT, SDK, and technical questions using internal engineering documentation."
    capabilities = [
        Capability(
            name="answer_tech_question",
            description="Answer a technical question (API, SDK, infra, tooling) using internal tech docs.",
            input_schema={
                "type": "object",
                "required": ["question"],
                "properties": {"question": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "citations": {"type": "array"},
                },
            },
        )
    ]
    supported_task_types = [TaskType.EMPLOYEE_QUESTION]
    domain = KnowledgeDomain.IT

    def _build_graph(self):
        async def retrieve_node(state: _ITState) -> _ITState:
            assert self.retriever is not None
            chunks = await self.retriever.retrieve(
                state["question"], domain=self.domain, top_k=5
            )
            self.log.info("it.retrieved", chunk_count=len(chunks))
            return {"retrieved": chunks}

        async def synthesize_node(state: _ITState) -> _ITState:
            retrieved = state.get("retrieved", [])
            if not retrieved:
                return {
                    "answer": (
                        f"{NO_INFO_MARKER} (no relevant documents in the IT "
                        "knowledge base for this question)."
                    ),
                    "citations": [],
                }
            sources_block = format_sources(retrieved)
            messages = [
                {"role": "system", "content": IT_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"SOURCES:\n{sources_block}\n\nQUESTION: {state['question']}"
                    ),
                },
            ]
            answer = await self.llm.chat(messages)
            citations = extract_citations(answer, retrieved)
            self.log.info(
                "it.synthesized", chars=len(answer), citation_count=len(citations)
            )
            return {"answer": answer, "citations": citations}

        builder = StateGraph(_ITState)
        builder.add_node("retrieve", retrieve_node)
        builder.add_node("synthesize", synthesize_node)
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "synthesize")
        builder.add_edge("synthesize", END)
        return builder.compile()

    async def run(self, task: Task) -> TaskResult:
        assert isinstance(task.input, EmployeeQuestionInput), (
            f"ITSpecialist expects EmployeeQuestionInput; got {type(task.input).__name__}"
        )
        self.log.info("it.run_start", task_id=str(task.id))
        result = await self._graph.ainvoke({"question": task.input.question})
        answer = result.get("answer", "")
        citations = result.get("citations", [])
        confidence = 0.3 if NO_INFO_MARKER in answer else 0.85
        self.log.info(
            "it.run_done",
            task_id=str(task.id),
            citations=len(citations),
            confidence=confidence,
        )
        return TaskResult(summary=answer, citations=citations, confidence=confidence)

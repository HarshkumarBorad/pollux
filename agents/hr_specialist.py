"""HR Specialist.

Standard RAG flow: retrieve from HR-domain chunks → synthesize answer with
[N] citations → translate to TaskResult.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import BaseAgent
from agents.prompts import HR_SYSTEM
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

NO_INFO_MARKER = "I don't have enough information in our HR docs"


class _HRState(TypedDict, total=False):
    question: str
    retrieved: list[RetrievedChunk]
    answer: str
    citations: list[Citation]


class HRSpecialist(BaseAgent):
    id = "hr_specialist"
    name = "HR Specialist"
    description = "Answers HR policy / onboarding / leave questions using internal HR documents."
    capabilities = [
        Capability(
            name="answer_hr_question",
            description="Answer an employee's HR question using internal HR docs.",
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
    domain = KnowledgeDomain.HR

    def _build_graph(self):
        async def retrieve_node(state: _HRState) -> _HRState:
            assert self.retriever is not None
            chunks = await self.retriever.retrieve(
                state["question"], domain=self.domain, top_k=5
            )
            self.log.info("hr.retrieved", chunk_count=len(chunks))
            return {"retrieved": chunks}

        async def synthesize_node(state: _HRState) -> _HRState:
            retrieved = state.get("retrieved", [])
            if not retrieved:
                # No chunks → return the canned no-info answer; skip the LLM.
                return {
                    "answer": (
                        f"{NO_INFO_MARKER} (no relevant documents in the HR "
                        "knowledge base for this question)."
                    ),
                    "citations": [],
                }
            sources_block = format_sources(retrieved)
            messages = [
                {"role": "system", "content": HR_SYSTEM},
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
                "hr.synthesized",
                chars=len(answer),
                citation_count=len(citations),
            )
            return {"answer": answer, "citations": citations}

        builder = StateGraph(_HRState)
        builder.add_node("retrieve", retrieve_node)
        builder.add_node("synthesize", synthesize_node)
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "synthesize")
        builder.add_edge("synthesize", END)
        return builder.compile()

    async def run(self, task: Task) -> TaskResult:
        assert isinstance(task.input, EmployeeQuestionInput), (
            f"HRSpecialist expects EmployeeQuestionInput; got {type(task.input).__name__}"
        )
        self.log.info("hr.run_start", task_id=str(task.id))
        result = await self._graph.ainvoke({"question": task.input.question})
        answer = result.get("answer", "")
        citations = result.get("citations", [])
        # Confidence heuristic: drop to 0.3 if the no-info marker fired.
        confidence = 0.3 if NO_INFO_MARKER in answer else 0.85
        self.log.info(
            "hr.run_done",
            task_id=str(task.id),
            citations=len(citations),
            confidence=confidence,
        )
        return TaskResult(
            summary=answer,
            citations=citations,
            confidence=confidence,
        )

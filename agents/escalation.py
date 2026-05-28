"""Escalation / QA Agent.

A meta-agent. Doesn't process tasks itself — it reviews the output of another
agent and returns a verdict:

    ship     — confidence high enough to send the answer as-is.
    revise   — confidence in the grey zone; flag for human review but still
               return the draft. (Phase 5's orchestrator may loop on this;
               Phase 4 treats it as escalate.)
    escalate — low confidence or the agent emitted the canonical "I don't
               have enough information" marker. Hand off to a human.

Phase 4 uses pure rule-based heuristics — fast, deterministic, debuggable.
Phase 10 will swap in an optional LLM-as-judge that grades the answer
against the original question for a stronger signal.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import BaseAgent
from core.tasks import Capability, Task, TaskResult, TaskType

# Strings the specialists emit when their knowledge base lacks the answer.
# Adding new markers here is the only place to keep in sync.
NO_INFO_MARKERS = (
    "I don't have enough information in our HR docs",
    "I don't have enough information in our technical docs",
)

Verdict = Literal["ship", "revise", "escalate"]

# Confidence thresholds. Tweak per-domain in Phase 10 if needed.
ESCALATE_BELOW = 0.4
REVISE_BELOW = 0.7


class _EscalationState(TypedDict, total=False):
    task: Task
    verdict: Verdict
    reasoning: str
    adjusted_confidence: float


class EscalationAgent(BaseAgent):
    id = "escalation"
    name = "Escalation / QA"
    description = (
        "Reviews specialist task results and decides verdict: ship, revise, "
        "or escalate to a human."
    )
    capabilities = [
        Capability(
            name="review_task_result",
            description="Review a processed task and return ship / revise / escalate verdict.",
            input_schema={
                "type": "object",
                "required": ["task"],
                "properties": {"task": {"type": "object"}},
            },
            output_schema={
                "type": "object",
                "properties": {
                    "verdict": {"enum": ["ship", "revise", "escalate"]},
                    "reasoning": {"type": "string"},
                    "adjusted_confidence": {"type": "number"},
                },
            },
        )
    ]
    # Doesn't accept incoming task types directly — only runs *after* a
    # specialist. Listed empty so the registry doesn't double-claim ownership.
    supported_task_types = []
    domain = None
    llm_temperature = 0.0

    def _build_graph(self):
        async def review_node(state: _EscalationState) -> _EscalationState:
            task: Task = state["task"]
            result = task.result

            if result is None or task.error:
                return {
                    "verdict": "escalate",
                    "reasoning": (
                        task.error
                        if task.error
                        else "Task has no result. Escalating."
                    ),
                    "adjusted_confidence": 0.0,
                }

            summary = result.summary or ""
            no_info = any(marker in summary for marker in NO_INFO_MARKERS)
            if no_info:
                return {
                    "verdict": "escalate",
                    "reasoning": (
                        "Specialist returned the canonical no-information "
                        "marker — knowledge base lacks the answer. Routing "
                        "to a human."
                    ),
                    "adjusted_confidence": 0.2,
                }

            confidence = result.confidence if result.confidence is not None else 0.5

            if confidence < ESCALATE_BELOW:
                return {
                    "verdict": "escalate",
                    "reasoning": (
                        f"Specialist confidence {confidence:.2f} is below "
                        f"the {ESCALATE_BELOW:.2f} escalate threshold."
                    ),
                    "adjusted_confidence": confidence,
                }
            if confidence < REVISE_BELOW:
                return {
                    "verdict": "revise",
                    "reasoning": (
                        f"Specialist confidence {confidence:.2f} is in the "
                        f"grey zone ({ESCALATE_BELOW:.2f}–{REVISE_BELOW:.2f}). "
                        "Recommend human review before sending."
                    ),
                    "adjusted_confidence": confidence,
                }
            return {
                "verdict": "ship",
                "reasoning": (
                    f"Specialist confidence {confidence:.2f} clears the "
                    f"{REVISE_BELOW:.2f} ship threshold. Cleared for delivery."
                ),
                "adjusted_confidence": confidence,
            }

        builder = StateGraph(_EscalationState)
        builder.add_node("review", review_node)
        builder.add_edge(START, "review")
        builder.add_edge("review", END)
        return builder.compile()

    async def run(self, task: Task) -> TaskResult:
        self.log.info(
            "escalation.run_start",
            task_id=str(task.id),
            has_result=task.result is not None,
            specialist_confidence=task.result.confidence if task.result else None,
        )
        state = await self._graph.ainvoke({"task": task})
        verdict = state.get("verdict", "escalate")
        reasoning = state.get("reasoning", "")
        adjusted = state.get("adjusted_confidence", 0.0)
        self.log.info(
            "escalation.run_done",
            task_id=str(task.id),
            verdict=verdict,
            adjusted_confidence=adjusted,
        )
        return TaskResult(
            summary=reasoning,
            artifacts={
                "verdict": verdict,
                "adjusted_confidence": adjusted,
            },
            confidence=adjusted,
        )

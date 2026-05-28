"""Ops Planner.

Two-stage:

  summarize transcript (LLM) → extract action items as JSON (LLM)

No knowledge-base retrieval — meeting transcripts are self-contained input.
The Coordinator in Phase 4 may upgrade this agent's LLM to OpenAI when
OPENAI_API_KEY is set (per the user-confirmed design: HF for specialists,
OpenAI fallback only for Coordinator + OpsPlanner where stronger reasoning
matters).
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import BaseAgent
from agents.prompts import OPS_PLANNER_PLAN, OPS_PLANNER_SUMMARY
from agents.utils import parse_json_response
from core.tasks import (
    Capability,
    OpsWorkflowInput,
    Task,
    TaskResult,
    TaskType,
)

# Cap the transcript passed to the planner so very long meetings don't blow
# the LLM context. Production setups would chunk + map-reduce; this is the
# simple version.
TRANSCRIPT_PLAN_MAX_CHARS = 3000


class _OpsPlannerState(TypedDict, total=False):
    transcript: str
    meeting_title: str
    attendees: list[str]
    summary: str
    subtasks: list[dict]


class OpsPlanner(BaseAgent):
    id = "ops_planner"
    name = "Ops Planner"
    description = (
        "Decomposes meeting transcripts into actionable subtasks with "
        "assignees, priorities, and deadlines."
    )
    capabilities = [
        Capability(
            name="plan_from_meeting",
            description="Summarize a meeting transcript and extract action items as structured JSON.",
            input_schema={
                "type": "object",
                "required": ["transcript"],
                "properties": {
                    "transcript": {"type": "string"},
                    "meeting_title": {"type": "string"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "subtasks": {"type": "array"},
                },
            },
        )
    ]
    supported_task_types = [TaskType.OPS_WORKFLOW]
    domain = None  # No knowledge binding.
    llm_max_tokens = 1200
    # Low temperature for the JSON-structured plan step keeps output well-formed.
    llm_temperature = 0.1

    def _build_graph(self):
        async def summarize_node(state: _OpsPlannerState) -> _OpsPlannerState:
            messages = [
                {"role": "system", "content": OPS_PLANNER_SUMMARY},
                {"role": "user", "content": state["transcript"]},
            ]
            summary = await self.llm.chat(messages, max_tokens=600, temperature=0.2)
            self.log.info("ops.summarized", chars=len(summary))
            return {"summary": summary}

        async def plan_node(state: _OpsPlannerState) -> _OpsPlannerState:
            transcript_excerpt = state["transcript"][:TRANSCRIPT_PLAN_MAX_CHARS]
            attendees = state.get("attendees") or []
            attendees_block = (
                f"ATTENDEES: {', '.join(attendees)}\n" if attendees else ""
            )
            messages = [
                {"role": "system", "content": OPS_PLANNER_PLAN},
                {
                    "role": "user",
                    "content": (
                        f"{attendees_block}"
                        f"MEETING SUMMARY:\n{state['summary']}\n\n"
                        f"TRANSCRIPT (excerpt for reference):\n{transcript_excerpt}"
                    ),
                },
            ]
            raw = await self.llm.chat(messages, max_tokens=1200, temperature=0.1)
            parsed = parse_json_response(raw, default={"subtasks": []})
            if not isinstance(parsed, dict):
                self.log.warning("ops.plan_parse_unexpected_type", value_type=type(parsed).__name__)
                parsed = {"subtasks": []}
            subtasks = parsed.get("subtasks", [])
            if not isinstance(subtasks, list):
                subtasks = []
            self.log.info("ops.planned", subtask_count=len(subtasks))
            return {"subtasks": subtasks}

        builder = StateGraph(_OpsPlannerState)
        builder.add_node("summarize", summarize_node)
        builder.add_node("plan", plan_node)
        builder.add_edge(START, "summarize")
        builder.add_edge("summarize", "plan")
        builder.add_edge("plan", END)
        return builder.compile()

    async def run(self, task: Task) -> TaskResult:
        assert isinstance(task.input, OpsWorkflowInput), (
            f"OpsPlanner expects OpsWorkflowInput; got {type(task.input).__name__}"
        )
        self.log.info("ops.run_start", task_id=str(task.id))
        result = await self._graph.ainvoke(
            {
                "transcript": task.input.transcript,
                "meeting_title": task.input.meeting_title or "Untitled",
                "attendees": task.input.attendees or [],
            }
        )
        summary = result.get("summary", "")
        subtasks = result.get("subtasks", [])
        # Confidence: low when we couldn't parse JSON at all (empty list might
        # also be a legitimate "nothing actionable" though). Use 0.5 as floor
        # so downstream confidence-gating doesn't auto-escalate.
        confidence = 0.5 if not subtasks else 0.8
        self.log.info(
            "ops.run_done",
            task_id=str(task.id),
            subtasks=len(subtasks),
            confidence=confidence,
        )
        return TaskResult(
            summary=summary,
            artifacts={
                "subtasks": subtasks,
                "meeting_title": task.input.meeting_title or "Untitled",
                "attendees": task.input.attendees or [],
            },
            confidence=confidence,
        )

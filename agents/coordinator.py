"""Coordinator Agent.

Entry point for every task. Picks the right specialist to handle it.

Routing strategy:
- `CUSTOMER_SUPPORT` → customer_facing      (rule, unambiguous)
- `OPS_WORKFLOW`     → ops_planner          (rule, unambiguous)
- `EMPLOYEE_QUESTION` → hr_specialist OR it_specialist
                       — LLM classifies the question by topic.

The LLM here is `make_coordinator_llm()` — OpenAI if `OPENAI_API_KEY` is set,
otherwise HF Inference. Routing benefits more from a strong reasoner than
the specialist agents do; getting the route wrong wastes downstream work.

If the LLM fails or returns invalid JSON, the Coordinator defaults to
hr_specialist (safer than failing the whole pipeline). The Escalation agent
downstream will catch genuinely bad answers regardless.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import BaseAgent
from agents.llm import make_coordinator_llm
from agents.prompts import COORDINATOR_ROUTING
from agents.utils import parse_json_response
from core.tasks import (
    Capability,
    CustomerSupportInput,
    EmployeeQuestionInput,
    OpsWorkflowInput,
    Task,
    TaskResult,
    TaskType,
)


# Task types with a single valid handler — no LLM needed for these.
RULE_BASED_ROUTING: dict[TaskType, str] = {
    TaskType.CUSTOMER_SUPPORT: "customer_facing",
    TaskType.OPS_WORKFLOW: "ops_planner",
}

# Fallback when LLM classification fails or returns garbage.
LLM_DEFAULT_AGENT = "hr_specialist"


class _CoordinatorState(TypedDict, total=False):
    task: Task
    routed_to: str
    reasoning: str


class CoordinatorAgent(BaseAgent):
    id = "coordinator"
    name = "Coordinator"
    description = (
        "Routes incoming tasks to the right specialist. Uses LLM "
        "classification for ambiguous cases (e.g. HR vs IT employee questions)."
    )
    capabilities = [
        Capability(
            name="route_task",
            description="Pick the right specialist agent for an incoming task.",
            input_schema={
                "type": "object",
                "required": ["task"],
                "properties": {"task": {"type": "object"}},
            },
            output_schema={
                "type": "object",
                "properties": {
                    "routed_to": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
            },
        )
    ]
    supported_task_types = [
        TaskType.CUSTOMER_SUPPORT,
        TaskType.EMPLOYEE_QUESTION,
        TaskType.OPS_WORKFLOW,
    ]
    domain = None
    llm_temperature = 0.0  # deterministic routing
    llm_max_tokens = 200

    def _make_llm(self):
        # Coordinator prefers OpenAI when available (routing accuracy matters).
        return make_coordinator_llm(
            max_tokens=type(self).llm_max_tokens,
            temperature=type(self).llm_temperature,
        )

    def _build_graph(self):
        async def classify_node(state: _CoordinatorState) -> _CoordinatorState:
            task: Task = state["task"]

            # 1. Rule-based shortcut for unambiguous task types.
            if task.type in RULE_BASED_ROUTING:
                routed_to = RULE_BASED_ROUTING[task.type]
                self.log.info(
                    "coordinator.rule_routed",
                    task_id=str(task.id),
                    task_type=task.type.value,
                    routed_to=routed_to,
                )
                return {
                    "routed_to": routed_to,
                    "reasoning": (
                        f"Rule-based: {task.type.value} → {routed_to}."
                    ),
                }

            # 2. EMPLOYEE_QUESTION needs LLM classification (HR vs IT).
            assert isinstance(task.input, EmployeeQuestionInput)
            question = task.input.question
            try:
                raw = await self.llm.chat(
                    [
                        {
                            "role": "user",
                            "content": COORDINATOR_ROUTING.format(question=question),
                        }
                    ]
                )
            except Exception as exc:
                self.log.warning(
                    "coordinator.llm_failed",
                    task_id=str(task.id),
                    error=str(exc),
                    fallback=LLM_DEFAULT_AGENT,
                )
                return {
                    "routed_to": LLM_DEFAULT_AGENT,
                    "reasoning": f"LLM classification failed ({exc}); defaulted to {LLM_DEFAULT_AGENT}.",
                }

            parsed = parse_json_response(raw, default={})
            category = (parsed.get("category") if isinstance(parsed, dict) else "") or ""
            reasoning = (
                parsed.get("reasoning")
                if isinstance(parsed, dict)
                else ""
            ) or "LLM did not provide reasoning."

            if category not in ("hr", "it"):
                self.log.warning(
                    "coordinator.invalid_category",
                    task_id=str(task.id),
                    raw_response=raw[:200],
                )
                return {
                    "routed_to": LLM_DEFAULT_AGENT,
                    "reasoning": f"LLM returned invalid category {category!r}; defaulted.",
                }

            routed_to = "hr_specialist" if category == "hr" else "it_specialist"
            self.log.info(
                "coordinator.llm_routed",
                task_id=str(task.id),
                routed_to=routed_to,
                reasoning=reasoning,
            )
            return {"routed_to": routed_to, "reasoning": reasoning}

        builder = StateGraph(_CoordinatorState)
        builder.add_node("classify", classify_node)
        builder.add_edge(START, "classify")
        builder.add_edge("classify", END)
        return builder.compile()

    async def run(self, task: Task) -> TaskResult:
        self.log.info(
            "coordinator.run_start",
            task_id=str(task.id),
            task_type=task.type.value,
        )
        state = await self._graph.ainvoke({"task": task})
        routed_to = state.get("routed_to", LLM_DEFAULT_AGENT)
        reasoning = state.get("reasoning", "")
        return TaskResult(
            summary=f"Routed to {routed_to}: {reasoning}",
            artifacts={"routed_to": routed_to, "reasoning": reasoning},
            confidence=0.9 if routed_to != LLM_DEFAULT_AGENT or task.type in RULE_BASED_ROUTING else 0.5,
        )

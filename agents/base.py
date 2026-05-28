"""BaseAgent — the shared shape for every Pollux specialist agent.

Design goals:

1. **Static metadata as class attributes.** `id`, `name`, `capabilities` etc.
   live on the class, so `Agent.agent_card()` works without instantiating —
   useful for the MCP server (Phase 6), A2A discovery (Phase 7), and unit
   tests that don't have an HF_TOKEN.

2. **Runtime wiring in `__init__`.** LLM client, retriever, compiled
   LangGraph — these only get built when you actually intend to run the
   agent.

3. **One protocol-neutral `run(task)` entrypoint.** Returns a `TaskResult`.
   The MCP variant calls this from inside a tool handler; the A2A variant
   calls it from inside the per-agent endpoint. Same business logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Optional

from core.knowledge import KnowledgeDomain, Retriever
from core.tasks import AgentCard, Capability, Task, TaskResult, TaskType
from core.telemetry import get_logger

from agents.llm import HFChatLLM


class BaseAgent(ABC):
    """Abstract base. Subclasses declare metadata as class attributes and
    implement `_build_graph()` + `run()`.
    """

    # ----- Static metadata (must be overridden) ------------------------------

    id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    capabilities: ClassVar[list[Capability]] = []
    supported_task_types: ClassVar[list[TaskType]] = []
    domain: ClassVar[Optional[KnowledgeDomain]] = None
    version: ClassVar[str] = "0.1.0"

    # LLM tuning — subclasses can override.
    llm_max_tokens: ClassVar[int] = 512
    llm_temperature: ClassVar[float] = 0.2

    # ----- Lifecycle ---------------------------------------------------------

    def __init__(self) -> None:
        cls = type(self)
        if not cls.id:
            raise ValueError(
                f"{cls.__name__} must set the class attribute `id`."
            )
        if not cls.capabilities:
            raise ValueError(
                f"{cls.__name__} must declare at least one Capability."
            )

        self.log = get_logger(f"pollux.agents.{cls.id}")
        self.llm = self._make_llm()
        self.retriever: Optional[Retriever] = (
            Retriever() if cls.domain is not None else None
        )
        self._graph = self._build_graph()

    def _make_llm(self):
        """LLM factory hook. Default = HFChatLLM. Coordinator + OpsPlanner
        override this to prefer OpenAI when OPENAI_API_KEY is set."""
        return HFChatLLM(
            max_tokens=type(self).llm_max_tokens,
            temperature=type(self).llm_temperature,
        )

    # ----- Discovery ---------------------------------------------------------

    @classmethod
    def agent_card(cls) -> AgentCard:
        """Cross-protocol description. Same data, different wire format:
        MCP serializes each capability as a tool; A2A serializes the card
        as the agent's discovery document.
        """
        return AgentCard(
            id=cls.id,
            name=cls.name,
            description=cls.description,
            capabilities=list(cls.capabilities),
            supported_task_types=list(cls.supported_task_types),
            version=cls.version,
        )

    # ----- Subclass extension points -----------------------------------------

    @abstractmethod
    def _build_graph(self):
        """Return the compiled LangGraph state machine for this agent."""

    @abstractmethod
    async def run(self, task: Task) -> TaskResult:
        """Execute the agent's pipeline for a given task and return the result.

        Implementations should:
        1. Pull the right fields off `task.input` (which is a tagged union).
        2. Build the LangGraph initial state.
        3. `await self._graph.ainvoke(state)`.
        4. Translate the final state into a `TaskResult`.
        """

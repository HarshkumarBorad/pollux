"""A2A AgentCard builders.

Translates Pollux's internal `AgentCard` (defined in core/tasks/models.py)
into Google A2A's wire-format `AgentCard`. Same metadata, different schema —
A2A has stricter typing around Skills + Capabilities for its discovery
protocol.

Pollux's AgentCard is the source of truth; this layer only reshapes.
"""
from __future__ import annotations

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from agents import BaseAgent


def _slugify_skill_name(name: str) -> str:
    """`answer_hr_question` → `Answer HR Question`."""
    return name.replace("_", " ").title().replace("Hr", "HR").replace("It", "IT")


def build_card(agent_cls: type[BaseAgent], base_url: str) -> AgentCard:
    """Construct an A2A `AgentCard` for a Pollux agent class.

    `base_url` is the externally-visible URL of the A2A server (e.g.
    `http://localhost:8003`); the agent's own URL ends up at
    `<base_url>/agents/<agent_id>`.
    """
    skills: list[AgentSkill] = []
    for cap in agent_cls.capabilities:
        examples: list[str] = []
        for ex in cap.examples or []:
            inp = ex.input if isinstance(ex.input, dict) else {}
            # Surface the most-common input keys as one-line examples.
            for key in ("question", "subject", "transcript", "text"):
                if key in inp and isinstance(inp[key], str):
                    examples.append(inp[key])
                    break

        tags: list[str] = []
        if agent_cls.domain is not None:
            tags.append(agent_cls.domain.value)
        for tt in agent_cls.supported_task_types:
            tags.append(tt.value)
        # Dedupe preserving order.
        seen: set[str] = set()
        unique_tags = [t for t in tags if not (t in seen or seen.add(t))]

        skills.append(
            AgentSkill(
                id=cap.name,
                name=_slugify_skill_name(cap.name),
                description=cap.description,
                tags=unique_tags or [agent_cls.id],
                examples=examples or None,
            )
        )

    return AgentCard(
        name=agent_cls.name,
        description=agent_cls.description,
        url=f"{base_url}/agents/{agent_cls.id}",
        version=agent_cls.version,
        # A2A's protocol metadata
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        skills=skills,
        default_input_modes=["text", "data"],
        default_output_modes=["text", "data"],
    )

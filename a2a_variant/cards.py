"""A2A AgentCard builders.

Translates Pollux's internal `AgentCard` (defined in core/tasks/models.py)
into the current a2a-sdk's protobuf-based AgentCard wire format. The two
layers stay decoupled — Pollux capabilities are the source of truth; this
module only reshapes.

Notable change from older a2a-sdk versions: the top-level `url` field is
gone. Agents now expose a list of `supported_interfaces`, each with its
own URL, protocol binding, and protocol version.
"""
from __future__ import annotations

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)

from agents import BaseAgent

# Current A2A wire constants.
JSONRPC_BINDING = "JSONRPC"
A2A_PROTOCOL_VERSION = "1.0"


def _slugify_skill_name(name: str) -> str:
    """`answer_hr_question` → `Answer HR Question`."""
    return name.replace("_", " ").title().replace("Hr", "HR").replace("It", "IT")


def _build_skills(agent_cls: type[BaseAgent]) -> list[AgentSkill]:
    skills: list[AgentSkill] = []
    for cap in agent_cls.capabilities:
        examples: list[str] = []
        for ex in cap.examples or []:
            inp = ex.input if isinstance(ex.input, dict) else {}
            for key in ("question", "subject", "transcript", "text"):
                if key in inp and isinstance(inp[key], str):
                    examples.append(inp[key])
                    break

        # Tags = domain + task types (downstream matchmaking).
        tags: list[str] = []
        if agent_cls.domain is not None:
            tags.append(agent_cls.domain.value)
        for tt in agent_cls.supported_task_types:
            tags.append(tt.value)
        seen: set[str] = set()
        unique_tags = [t for t in tags if not (t in seen or seen.add(t))]

        skills.append(
            AgentSkill(
                id=cap.name,
                name=_slugify_skill_name(cap.name),
                description=cap.description,
                tags=unique_tags or [agent_cls.id],
                examples=examples,  # repeated proto fields accept [] cleanly
            )
        )
    return skills


def build_card(agent_cls: type[BaseAgent], base_url: str) -> AgentCard:
    """Construct an A2A `AgentCard` (protobuf message) for a Pollux agent.

    `base_url` is the externally-visible URL of the A2A server. The agent's
    JSON-RPC endpoint URL ends up at `<base_url>/agents/<agent_id>/`.
    """
    interface = AgentInterface(
        url=f"{base_url}/agents/{agent_cls.id}/",
        protocol_binding=JSONRPC_BINDING,
        protocol_version=A2A_PROTOCOL_VERSION,
    )

    return AgentCard(
        name=agent_cls.name,
        description=agent_cls.description,
        version=agent_cls.version,
        supported_interfaces=[interface],
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            extended_agent_card=False,
        ),
        skills=_build_skills(agent_cls),
        default_input_modes=["text", "data"],
        default_output_modes=["text", "data"],
    )

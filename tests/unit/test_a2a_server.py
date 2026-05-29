"""Smoke tests for the A2A variant.

Confirms the variant module imports cleanly, the Starlette app builds with
every non-meta agent mounted, and the Agent Card builder produces the right
shape for one specialist. Real protocol round-trips need network + HF; those
live in Phase 10's integration tests.
"""
from __future__ import annotations


EXPECTED_MOUNT_PATHS = {
    "/agents/hr_specialist",
    "/agents/it_specialist",
    "/agents/customer_facing",
    "/agents/ops_planner",
    "/agents/coordinator",
}


def test_a2a_module_imports_cleanly() -> None:
    """If any import in cards.py / executor.py / server.py is broken, this
    catches it — including a version mismatch in the `a2a` SDK API."""
    from a2a_variant import server  # noqa: F401


def test_build_app_mounts_every_non_meta_agent() -> None:
    """The app should mount one A2A sub-app per public agent and skip
    Escalation (which is review-only, not a peer)."""
    from a2a_variant.server import build_app

    app = build_app(base_url="http://test.example:8003")
    mount_paths = {
        getattr(route, "path", "") for route in app.routes
        if route.__class__.__name__ == "Mount"
    }
    missing = EXPECTED_MOUNT_PATHS - mount_paths
    assert not missing, f"Missing A2A mounts: {missing}"

    # Escalation must NOT be exposed.
    assert "/agents/escalation" not in mount_paths


def test_build_card_for_hr_specialist() -> None:
    """Pollux capabilities translate to A2A skills with the right shape."""
    from a2a_variant.cards import build_card
    from agents import HRSpecialist

    card = build_card(HRSpecialist, base_url="http://test.example:8003")
    assert card.name == "HR Specialist"
    assert card.url == "http://test.example:8003/agents/hr_specialist"
    assert card.capabilities.streaming is True

    # At least one Skill, with the right id and a non-empty tag list.
    assert card.skills, "Expected at least one skill"
    skill = card.skills[0]
    assert skill.id == "answer_hr_question"
    assert skill.tags  # tags come from domain + supported_task_types
    assert "hr" in skill.tags or "employee_question" in skill.tags

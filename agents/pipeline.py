"""End-to-end task pipeline.

    Coordinator (route) → Specialist (process) → Escalation (verdict)

Phase 4 keeps this in-memory — no DB, no retries, no queueing. Phase 5
wraps a persistent task store + retry / timeout logic around the same
`run_task()` function.

The pipeline mutates `task.status`, `task.assigned_agent`, `task.result`,
and `task.error` in place, then returns the same Task instance. Callers
can inspect the final state and decide what to do (ship the answer,
notify a human, retry, etc.).
"""
from __future__ import annotations

from core.tasks import Task, TaskStatus
from core.telemetry import get_logger

log = get_logger("pollux.agents.pipeline")


async def run_task(task: Task) -> Task:
    """Execute Coordinator → Specialist → Escalation for a single task.

    Returns the same Task object with `status`, `assigned_agent`, `result`,
    and (on failure) `error` populated. Final status is one of:
        COMPLETED  — Escalation said ship.
        ESCALATED  — Escalation said escalate or revise.
        FAILED     — Coordinator couldn't route or specialist raised.
    """
    # Lazy import — avoids a circular module load between __init__ and pipeline.
    from agents import get_agent

    log.info(
        "pipeline.start",
        task_id=str(task.id),
        task_type=task.type.value,
    )
    task.status = TaskStatus.IN_PROGRESS

    # ----- 1. Coordinator routes -----
    try:
        coordinator = get_agent("coordinator")
        route_result = await coordinator.run(task)
    except Exception as exc:
        task.status = TaskStatus.FAILED
        task.error = f"Coordinator failed: {exc}"
        log.error("pipeline.coordinator_failed", task_id=str(task.id), error=str(exc))
        return task

    routed_to = route_result.artifacts.get("routed_to")
    if not routed_to:
        task.status = TaskStatus.FAILED
        task.error = "Coordinator did not pick an agent."
        return task
    task.assigned_agent = routed_to
    log.info("pipeline.routed", task_id=str(task.id), routed_to=routed_to)

    # ----- 2. Specialist processes -----
    try:
        specialist = get_agent(routed_to)
        specialist_result = await specialist.run(task)
        task.result = specialist_result
    except Exception as exc:
        task.status = TaskStatus.FAILED
        task.error = f"Specialist {routed_to!r} failed: {exc}"
        log.error(
            "pipeline.specialist_failed",
            task_id=str(task.id),
            routed_to=routed_to,
            error=str(exc),
        )
        return task

    # ----- 3. Escalation QA -----
    try:
        escalation = get_agent("escalation")
        qa_result = await escalation.run(task)
    except Exception as exc:
        # QA failure shouldn't lose the specialist's work — log it and treat
        # the result as escalate (safest for a missing verdict).
        log.warning(
            "pipeline.qa_failed_falling_back_to_escalate",
            task_id=str(task.id),
            error=str(exc),
        )
        task.status = TaskStatus.ESCALATED
        return task

    verdict = qa_result.artifacts.get("verdict", "escalate")
    # Preserve QA verdict + reasoning in the task result for downstream review.
    if task.result is not None:
        task.result.artifacts["qa_verdict"] = verdict
        task.result.artifacts["qa_reasoning"] = qa_result.summary
        if qa_result.confidence is not None:
            task.result.confidence = qa_result.confidence

    if verdict == "ship":
        task.status = TaskStatus.COMPLETED
    else:
        # "revise" and "escalate" both terminate as ESCALATED in Phase 4.
        # Phase 5's orchestrator can loop on "revise" if desired.
        task.status = TaskStatus.ESCALATED

    log.info(
        "pipeline.done",
        task_id=str(task.id),
        final_status=task.status.value,
        routed_to=routed_to,
        verdict=verdict,
    )
    return task

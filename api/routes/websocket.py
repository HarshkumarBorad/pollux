"""WebSocket route for live task progress streaming.

    GET ws://host/tasks/{task_id}/stream

The connection sends a `status` envelope on connect (initial snapshot),
then `event` envelopes for every new entry added to `task_events`, and
finally a `result` envelope when the task reaches a terminal status.

Implementation is poll-based on top of the SQLite event log — simple,
single-process, no pub/sub infrastructure required. Phase 10 may swap in
an asyncio.Queue per-task or a Redis pubsub if multi-replica deploys
arrive.
"""
from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from api.dependencies import get_orchestrator, get_session_factory_dep
from api.schemas import WSEvent
from core.tasks.models import TaskStatus
from core.tasks.repository import TaskRepository
from core.telemetry import get_logger

log = get_logger("pollux.api.websocket")

router = APIRouter()

# Status values that mean "no more updates coming."
TERMINAL_STATUSES: set[TaskStatus] = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.ESCALATED,
}

# Tunables.
POLL_INTERVAL_SECONDS = 0.5
STREAM_TIMEOUT_SECONDS = 600  # 10 min cap to prevent runaway connections


async def _send(ws: WebSocket, kind: str, data: dict) -> None:
    """Send a WSEvent — keeps the envelope shape consistent everywhere."""
    await ws.send_json(WSEvent(type=kind, data=data).model_dump(mode="json"))


@router.websocket("/tasks/{task_id}/stream")
async def task_stream(
    websocket: WebSocket,
    task_id: str,
    orchestrator=Depends(get_orchestrator),
    session_factory=Depends(get_session_factory_dep),
) -> None:
    await websocket.accept()

    # Validate the path param up front.
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        await _send(websocket, "error", {"detail": f"Invalid task id: {task_id!r}"})
        await websocket.close()
        return

    # Initial snapshot.
    task = await orchestrator.get(task_uuid)
    if task is None:
        await _send(websocket, "error", {"detail": f"Task {task_id} not found"})
        await websocket.close()
        return

    await _send(websocket, "status", task.model_dump(mode="json"))

    if task.status in TERMINAL_STATUSES:
        await _send(websocket, "result", task.model_dump(mode="json"))
        await websocket.close()
        return

    # Poll loop — emit new events as they land, close when task completes.
    last_event_id = 0
    elapsed = 0.0
    log.info("ws.stream_start", task_id=task_id, initial_status=task.status.value)

    try:
        while elapsed < STREAM_TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

            # Fetch new events.
            async with session_factory() as session:
                events = await TaskRepository(session).list_events(task_uuid)
            for event in events:
                if event.id <= last_event_id:
                    continue
                await _send(
                    websocket,
                    "event",
                    {
                        "id": event.id,
                        "event_type": event.event_type,
                        "payload": event.payload or {},
                        "created_at": event.created_at.isoformat(),
                    },
                )
                last_event_id = event.id

            # Check for terminal status.
            task = await orchestrator.get(task_uuid)
            if task is None:
                await _send(websocket, "error", {"detail": "Task disappeared mid-stream"})
                break
            if task.status in TERMINAL_STATUSES:
                await _send(websocket, "result", task.model_dump(mode="json"))
                log.info(
                    "ws.stream_done",
                    task_id=task_id,
                    final_status=task.status.value,
                    elapsed_seconds=round(elapsed, 1),
                )
                break
        else:
            # Hit the timeout.
            await _send(
                websocket,
                "error",
                {"detail": f"Stream exceeded {STREAM_TIMEOUT_SECONDS}s timeout; task still running"},
            )
            log.warning("ws.stream_timeout", task_id=task_id)
    except WebSocketDisconnect:
        log.info("ws.client_disconnected", task_id=task_id)
        return

    try:
        await websocket.close()
    except Exception:
        # Connection already closed by the client side — fine.
        pass

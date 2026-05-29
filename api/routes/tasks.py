"""Task submission + inspection routes.

Submission is async by default — POST returns immediately with a 202 and a
task_id, the client subscribes to the WebSocket for live progress. Set
`?wait=true` to block until the pipeline completes (useful for non-interactive
clients like scripts).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from api.dependencies import (
    get_orchestrator,
    get_session_factory_dep,
    require_api_key,
)
from api.schemas import (
    SubmitMeetingRequest,
    SubmitQuestionRequest,
    SubmitResponse,
    SubmitTicketRequest,
    TaskDetailResponse,
    TaskEventOut,
    TaskListResponse,
)
from core.tasks.models import (
    CustomerSupportInput,
    EmployeeQuestionInput,
    OpsWorkflowInput,
    Task,
    TaskStatus,
    TaskType,
)
from core.tasks.repository import TaskRepository

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_api_key)])


def _links(task_id: UUID) -> dict[str, str]:
    """Build the polling URL + WebSocket URL pair returned in submit responses."""
    return {
        "location": f"/tasks/{task_id}",
        "stream": f"/tasks/{task_id}/stream",
    }


async def _submit(task: Task, wait: bool, orchestrator) -> SubmitResponse:
    if wait:
        final = await orchestrator.submit(task)
        return SubmitResponse(
            task_id=final.id,
            status=final.status,
            assigned_agent=final.assigned_agent,
            sync=True,
            task=final,
            **_links(final.id),
        )
    submitted = await orchestrator.submit_async(task)
    return SubmitResponse(
        task_id=submitted.id,
        status=submitted.status,
        assigned_agent=submitted.assigned_agent,
        sync=False,
        task=None,
        **_links(submitted.id),
    )


# ----- submit endpoints --------------------------------------------------

@router.post(
    "/question",
    response_model=SubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an employee question",
)
async def submit_question(
    body: SubmitQuestionRequest,
    response: Response,
    wait: bool = Query(False, description="Block until pipeline completes."),
    orchestrator=Depends(get_orchestrator),
):
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(
            question=body.question,
            employee_id=body.employee_id,
            context=body.context,
        ),
    )
    out = await _submit(task, wait, orchestrator)
    response.status_code = status.HTTP_200_OK if wait else status.HTTP_202_ACCEPTED
    return out


@router.post(
    "/ticket",
    response_model=SubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a customer support ticket",
)
async def submit_ticket(
    body: SubmitTicketRequest,
    response: Response,
    wait: bool = Query(False, description="Block until pipeline completes."),
    orchestrator=Depends(get_orchestrator),
):
    task = Task(
        type=TaskType.CUSTOMER_SUPPORT,
        input=CustomerSupportInput(
            ticket_subject=body.subject,
            ticket_body=body.body,
            customer_id=body.customer_id,
            channel=body.channel,
        ),
    )
    out = await _submit(task, wait, orchestrator)
    response.status_code = status.HTTP_200_OK if wait else status.HTTP_202_ACCEPTED
    return out


@router.post(
    "/meeting",
    response_model=SubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a meeting transcript for action-item extraction",
)
async def submit_meeting(
    body: SubmitMeetingRequest,
    response: Response,
    wait: bool = Query(False, description="Block until pipeline completes."),
    orchestrator=Depends(get_orchestrator),
):
    task = Task(
        type=TaskType.OPS_WORKFLOW,
        input=OpsWorkflowInput(
            transcript=body.transcript,
            meeting_title=body.meeting_title,
            attendees=body.attendees,
        ),
    )
    out = await _submit(task, wait, orchestrator)
    response.status_code = status.HTTP_200_OK if wait else status.HTTP_202_ACCEPTED
    return out


# ----- inspection endpoints ----------------------------------------------

@router.get("", response_model=TaskListResponse, summary="List recent tasks")
async def list_tasks(
    status_filter: TaskStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    orchestrator=Depends(get_orchestrator),
):
    tasks = await orchestrator.list(status=status_filter, limit=limit)
    return TaskListResponse(tasks=tasks, count=len(tasks))


@router.get("/{task_id}", response_model=TaskDetailResponse, summary="Get task state + events")
async def get_task(
    task_id: UUID,
    orchestrator=Depends(get_orchestrator),
    session_factory=Depends(get_session_factory_dep),
):
    task = await orchestrator.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    async with session_factory() as session:
        repo = TaskRepository(session)
        events = await repo.list_events(task_id)
    return TaskDetailResponse(
        task=task,
        events=[
            TaskEventOut(
                id=e.id,
                event_type=e.event_type,
                payload=e.payload or {},
                created_at=e.created_at,
            )
            for e in events
        ],
    )

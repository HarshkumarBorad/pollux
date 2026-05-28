"""Repository CRUD tests with an in-memory SQLite database.

Each test sets up its own engine + tables — no shared state, no fixtures
leaking between tests. Slow only by SQLAlchemy's standards (≈50ms each).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.db.models import Base
from core.tasks.models import (
    CustomerSupportInput,
    EmployeeQuestionInput,
    OpsWorkflowInput,
    Task,
    TaskResult,
    TaskStatus,
    TaskType,
)
from core.tasks.repository import TaskRepository


@pytest_asyncio.fixture
async def session():
    """Fresh in-memory DB + a session bound to it. Tables are created per test
    so no test sees rows left over from a previous one."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_then_get(session: AsyncSession) -> None:
    repo = TaskRepository(session)
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question="What is the leave policy?"),
    )
    await repo.create(task)

    loaded = await repo.get(task.id)
    assert loaded is not None
    assert loaded.id == task.id
    assert isinstance(loaded.input, EmployeeQuestionInput)
    assert loaded.input.question == "What is the leave policy?"


@pytest.mark.asyncio
async def test_polymorphic_inputs_roundtrip(session: AsyncSession) -> None:
    repo = TaskRepository(session)
    tasks = [
        Task(
            type=TaskType.CUSTOMER_SUPPORT,
            input=CustomerSupportInput(
                ticket_subject="API 401", ticket_body="..."
            ),
        ),
        Task(
            type=TaskType.OPS_WORKFLOW,
            input=OpsWorkflowInput(
                transcript="Lina: ship the migration.", attendees=["Lina"]
            ),
        ),
    ]
    for t in tasks:
        await repo.create(t)

    listed = await repo.list()
    types = {t.input.task_type for t in listed}
    assert TaskType.CUSTOMER_SUPPORT in types
    assert TaskType.OPS_WORKFLOW in types


@pytest.mark.asyncio
async def test_update_persists_status_and_result(session: AsyncSession) -> None:
    repo = TaskRepository(session)
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question="?"),
    )
    await repo.create(task)

    task.status = TaskStatus.COMPLETED
    task.assigned_agent = "hr_specialist"
    task.result = TaskResult(summary="ok", confidence=0.9)
    await repo.update(task)

    reloaded = await repo.get(task.id)
    assert reloaded is not None
    assert reloaded.status == TaskStatus.COMPLETED
    assert reloaded.assigned_agent == "hr_specialist"
    assert reloaded.result is not None
    assert reloaded.result.summary == "ok"
    assert reloaded.result.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_list_filters_by_status(session: AsyncSession) -> None:
    repo = TaskRepository(session)
    pending = Task(type=TaskType.EMPLOYEE_QUESTION, input=EmployeeQuestionInput(question="a"))
    done = Task(type=TaskType.EMPLOYEE_QUESTION, input=EmployeeQuestionInput(question="b"))
    done.status = TaskStatus.COMPLETED
    await repo.create(pending)
    await repo.create(done)

    just_pending = await repo.list(status=TaskStatus.PENDING)
    just_done = await repo.list(status=TaskStatus.COMPLETED)
    assert {t.input.question for t in just_pending} == {"a"}
    assert {t.input.question for t in just_done} == {"b"}


@pytest.mark.asyncio
async def test_increment_counters_are_independent(session: AsyncSession) -> None:
    repo = TaskRepository(session)
    task = Task(type=TaskType.EMPLOYEE_QUESTION, input=EmployeeQuestionInput(question="?"))
    await repo.create(task)

    assert await repo.increment_retry(task.id) == 1
    assert await repo.increment_retry(task.id) == 2
    assert await repo.increment_revise(task.id) == 1

    retries, revises = await repo.get_counters(task.id)
    assert (retries, revises) == (2, 1)


@pytest.mark.asyncio
async def test_log_event_creates_ordered_history(session: AsyncSession) -> None:
    repo = TaskRepository(session)
    task = Task(type=TaskType.EMPLOYEE_QUESTION, input=EmployeeQuestionInput(question="?"))
    await repo.create(task)

    await repo.log_event(task.id, "submitted", {"mode": "sync"})
    await repo.log_event(task.id, "routed", {"to": "hr_specialist"})
    await repo.log_event(task.id, "done", {"final_status": "completed"})

    events = await repo.list_events(task.id)
    assert [e.event_type for e in events] == ["submitted", "routed", "done"]
    assert events[1].payload == {"to": "hr_specialist"}

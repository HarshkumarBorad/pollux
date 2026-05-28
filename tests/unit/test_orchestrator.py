"""Orchestrator retry + revise logic tests.

The real `run_task()` needs HF / OpenAI / ChromaDB — not network-friendly
for unit tests. We monkey-patch it with deterministic fakes that simulate
each branch (success, transient error, timeout, revise verdict).
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.db.models import Base
from core.tasks.models import (
    EmployeeQuestionInput,
    Task,
    TaskResult,
    TaskStatus,
    TaskType,
)
from core.tasks.repository import TaskRepository

from orchestrator import TaskOrchestrator


@pytest_asyncio.fixture
async def factory():
    """Returns an async session factory bound to a private in-memory DB."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def _task() -> Task:
    return Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question="?"),
    )


def _patch_run_task(monkeypatch, fake):
    """Replace `agents.pipeline.run_task` everywhere the orchestrator might
    import it from."""
    monkeypatch.setattr("orchestrator.runner.run_task", fake)


# ----- happy path -----

@pytest.mark.asyncio
async def test_submit_persists_and_completes(factory, monkeypatch) -> None:
    async def fake(task: Task) -> Task:
        task.status = TaskStatus.COMPLETED
        task.assigned_agent = "hr_specialist"
        task.result = TaskResult(summary="answer", confidence=0.9)
        task.result.artifacts["qa_verdict"] = "ship"
        return task

    _patch_run_task(monkeypatch, fake)

    orchestrator = TaskOrchestrator(session_factory=factory)
    task = _task()
    final = await orchestrator.submit(task)

    assert final.status == TaskStatus.COMPLETED
    assert final.assigned_agent == "hr_specialist"

    # Verify it actually landed in the DB.
    async with factory() as session:
        loaded = await TaskRepository(session).get(task.id)
        assert loaded is not None
        assert loaded.status == TaskStatus.COMPLETED


# ----- retry path -----

@pytest.mark.asyncio
async def test_transient_error_retries_then_succeeds(factory, monkeypatch) -> None:
    """First call raises, second succeeds. Orchestrator should retry and
    return the success."""
    calls = {"n": 0}

    async def fake(task: Task) -> Task:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient HF API error")
        task.status = TaskStatus.COMPLETED
        task.result = TaskResult(summary="ok", confidence=0.9)
        task.result.artifacts["qa_verdict"] = "ship"
        return task

    _patch_run_task(monkeypatch, fake)

    orchestrator = TaskOrchestrator(
        session_factory=factory, max_retries=2, revise_attempts=0
    )
    final = await orchestrator.submit(_task())
    assert calls["n"] == 2
    assert final.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_exhausted_retries_marks_failed(factory, monkeypatch) -> None:
    async def fake(task: Task) -> Task:
        raise RuntimeError("permanent boom")

    _patch_run_task(monkeypatch, fake)

    orchestrator = TaskOrchestrator(
        session_factory=factory, max_retries=2, revise_attempts=0
    )
    final = await orchestrator.submit(_task())
    assert final.status == TaskStatus.FAILED
    assert "permanent boom" in (final.error or "")


# ----- revise loop -----

@pytest.mark.asyncio
async def test_revise_verdict_triggers_one_more_run(factory, monkeypatch) -> None:
    """First run returns revise verdict; orchestrator should re-run once.
    Second run returns ship → COMPLETED."""
    calls = {"n": 0}

    async def fake(task: Task) -> Task:
        calls["n"] += 1
        if calls["n"] == 1:
            task.status = TaskStatus.ESCALATED  # set by pipeline on revise
            task.assigned_agent = "hr_specialist"
            task.result = TaskResult(summary="draft", confidence=0.5)
            task.result.artifacts["qa_verdict"] = "revise"
            return task
        # Second attempt — clean ship
        task.status = TaskStatus.COMPLETED
        task.result = TaskResult(summary="answer", confidence=0.9)
        task.result.artifacts["qa_verdict"] = "ship"
        return task

    _patch_run_task(monkeypatch, fake)

    orchestrator = TaskOrchestrator(
        session_factory=factory, max_retries=0, revise_attempts=1
    )
    final = await orchestrator.submit(_task())
    assert calls["n"] == 2
    assert final.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_revise_attempts_zero_means_no_loop(factory, monkeypatch) -> None:
    """With revise_attempts=0, a revise verdict is accepted as-is and the task
    ends up ESCALATED (its pipeline-set status)."""
    async def fake(task: Task) -> Task:
        task.status = TaskStatus.ESCALATED
        task.result = TaskResult(summary="draft", confidence=0.5)
        task.result.artifacts["qa_verdict"] = "revise"
        return task

    _patch_run_task(monkeypatch, fake)

    orchestrator = TaskOrchestrator(
        session_factory=factory, max_retries=0, revise_attempts=0
    )
    final = await orchestrator.submit(_task())
    assert final.status == TaskStatus.ESCALATED


# ----- timeout -----

@pytest.mark.asyncio
async def test_timeout_retries_then_fails(factory, monkeypatch) -> None:
    async def fake_slow(task: Task) -> Task:
        await asyncio.sleep(0.5)
        task.status = TaskStatus.COMPLETED
        return task

    _patch_run_task(monkeypatch, fake_slow)

    orchestrator = TaskOrchestrator(
        session_factory=factory,
        timeout=0.1,  # fires before fake_slow finishes
        max_retries=1,
        revise_attempts=0,
    )
    final = await orchestrator.submit(_task())
    assert final.status == TaskStatus.FAILED
    assert "timed out" in (final.error or "").lower()

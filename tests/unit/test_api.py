"""Smoke tests for the REST API.

Uses FastAPI's TestClient (sync httpx under the hood). All test orchestrator
state is in-memory; `run_task` is monkey-patched so we don't hit HF / OpenAI
during unit tests. Integration tests with real network round-trips live in
Phase 10.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.dependencies import get_orchestrator, get_session_factory_dep
from api.main import build_app
from core.db.models import Base
from core.tasks.models import (
    EmployeeQuestionInput,
    Task,
    TaskResult,
    TaskStatus,
    TaskType,
)
from orchestrator import TaskOrchestrator


# ----- shared fixtures ----------------------------------------------------

@pytest_asyncio.fixture
async def factory():
    """Async session factory bound to a fresh in-memory SQLite DB."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def app_with_fake_orchestrator(factory, monkeypatch):
    """Build the FastAPI app with an in-memory orchestrator that runs a
    fake pipeline. Returns the app and the orchestrator so tests can inspect
    persisted state."""

    async def fake_run_task(task: Task) -> Task:
        # Deterministic success — every task completes cleanly.
        task.status = TaskStatus.COMPLETED
        task.assigned_agent = "hr_specialist"
        task.result = TaskResult(summary="answer", confidence=0.9)
        task.result.artifacts["qa_verdict"] = "ship"
        return task

    monkeypatch.setattr("orchestrator.runner.run_task", fake_run_task)

    orchestrator = TaskOrchestrator(
        session_factory=factory,
        max_retries=0,
        revise_attempts=0,
    )

    app = build_app()
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_session_factory_dep] = lambda: factory
    yield app, orchestrator
    app.dependency_overrides.clear()


# ----- system routes -----------------------------------------------------

def test_health_is_ok_against_fresh_db(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["agents"] >= 5  # at least HR, IT, customer, ops, coordinator


def test_agents_lists_registered_agents(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    r = client.get("/agents")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 5
    names = {a["name"] for a in body["agents"]}
    assert "HR Specialist" in names
    assert "Coordinator" in names


# ----- task submission ---------------------------------------------------

def test_submit_question_sync_returns_task(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    r = client.post(
        "/tasks/question?wait=true",
        json={"question": "What is the leave policy?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sync"] is True
    assert body["status"] == "completed"
    assert body["task"] is not None
    assert body["task"]["result"]["summary"] == "answer"
    assert body["location"].startswith("/tasks/")
    assert body["stream"].endswith("/stream")


def test_submit_ticket_async_returns_202(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    r = client.post(
        "/tasks/ticket",
        json={"subject": "Cannot log in", "body": "401 since yesterday"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["sync"] is False
    assert body["task"] is None  # not ready yet
    assert body["task_id"]


def test_submit_meeting_validates_transcript(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    # Empty transcript should 422 (pydantic min_length=1).
    r = client.post("/tasks/meeting", json={"transcript": ""})
    assert r.status_code == 422


# ----- inspection --------------------------------------------------------

def test_list_tasks_after_submit(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    client.post("/tasks/question?wait=true", json={"question": "?"})

    r = client.get("/tasks")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert body["tasks"][0]["status"] == "completed"


def test_get_task_returns_events(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    submit = client.post("/tasks/question?wait=true", json={"question": "?"}).json()
    task_id = submit["task_id"]

    r = client.get(f"/tasks/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["task"]["id"] == task_id
    assert len(body["events"]) >= 2  # at minimum: submitted, done


def test_get_unknown_task_404s(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    r = client.get("/tasks/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ----- auth --------------------------------------------------------------

def test_auth_required_when_key_set(app_with_fake_orchestrator, monkeypatch) -> None:
    """When POLLUX_API_KEY is set, requests without the header are rejected."""
    app, _ = app_with_fake_orchestrator
    # Force a fresh config that has the key set.
    from core.config import get_config
    get_config.cache_clear()  # pydantic-settings + lru_cache
    monkeypatch.setenv("POLLUX_API_KEY", "secret-token")

    client = TestClient(app)
    # Without header — 401.
    r1 = client.post("/tasks/question?wait=true", json={"question": "?"})
    assert r1.status_code == 401
    # With header — 200.
    r2 = client.post(
        "/tasks/question?wait=true",
        json={"question": "?"},
        headers={"X-API-Key": "secret-token"},
    )
    assert r2.status_code == 200

    # Reset cached config so other tests aren't affected.
    get_config.cache_clear()


# ----- WebSocket ---------------------------------------------------------

def test_websocket_streams_status_then_result(app_with_fake_orchestrator) -> None:
    """When the task is already terminal at connect time (sync mode submit
    completed before the WS opened), the WS sends `status` then `result`
    then closes."""
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)

    submit = client.post("/tasks/question?wait=true", json={"question": "?"}).json()
    task_id = submit["task_id"]

    with client.websocket_connect(f"/tasks/{task_id}/stream") as ws:
        first = ws.receive_json()
        second = ws.receive_json()
        # The task is already COMPLETED, so we expect status then result.
        assert first["type"] == "status"
        assert first["data"]["status"] == "completed"
        assert second["type"] == "result"


def test_websocket_404s_for_unknown_task(app_with_fake_orchestrator) -> None:
    app, _ = app_with_fake_orchestrator
    client = TestClient(app)
    with client.websocket_connect(
        "/tasks/00000000-0000-0000-0000-000000000000/stream"
    ) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "not found" in msg["data"]["detail"].lower()

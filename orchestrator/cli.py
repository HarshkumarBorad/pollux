"""Orchestrator CLI — submit / list / status / history.

This is the persistent counterpart to `agents.cli task`. Use this when you
want each run logged in SQLite, retries handled, and a queryable task
history. Use `agents.cli task` for one-off in-memory testing.

Usage:
    :: Bootstrap the DB once
    python -m orchestrator.cli migrate

    :: Submit and wait
    python -m orchestrator.cli submit --type employee "What's the leave policy?"
    python -m orchestrator.cli submit --type customer --subject "..." --body "..."
    python -m orchestrator.cli submit --type ops --transcript-file ./meeting.txt

    :: Inspect
    python -m orchestrator.cli list                  # most recent 20 tasks
    python -m orchestrator.cli list --status escalated
    python -m orchestrator.cli status <task-id>
    python -m orchestrator.cli history <task-id>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from core import telemetry
from core.db.migrate import create_all_tables
from core.db.session import get_session_factory
from core.tasks.models import (
    CustomerSupportInput,
    EmployeeQuestionInput,
    OpsWorkflowInput,
    Task,
    TaskStatus,
    TaskType,
)
from core.tasks.repository import TaskRepository

from orchestrator import TaskOrchestrator


def _print_task(task: Task) -> None:
    print(f"  id           : {task.id}")
    print(f"  type         : {task.type.value}")
    print(f"  status       : {task.status.value}")
    print(f"  assigned_to  : {task.assigned_agent or '-'}")
    print(f"  created_at   : {task.created_at.isoformat()}")
    print(f"  updated_at   : {task.updated_at.isoformat()}")
    if task.error:
        print(f"  error        : {task.error}")
    if task.result is not None:
        print(f"  confidence   : {task.result.confidence}")
        print(f"  summary      : {task.result.summary[:200]}")
        verdict = task.result.artifacts.get("qa_verdict")
        if verdict:
            print(f"  qa_verdict   : {verdict}")


async def cmd_migrate(_args) -> int:
    await create_all_tables()
    print("Tables created (or already exist).")
    return 0


async def cmd_submit(args) -> int:
    task = _build_task(args)
    if task is None:
        return 1
    orchestrator = TaskOrchestrator()
    print(f"Submitting task ({task.type.value})...\n")
    final = await orchestrator.submit(task)
    print("\n" + "=" * 72)
    _print_task(final)
    if final.result is not None:
        print("=" * 72)
        print(final.result.summary)
    print("=" * 72)
    return 0 if final.status in {TaskStatus.COMPLETED, TaskStatus.ESCALATED} else 1


async def cmd_list(args) -> int:
    orchestrator = TaskOrchestrator()
    status = TaskStatus(args.status) if args.status else None
    tasks = await orchestrator.list(status=status, limit=args.limit)
    if not tasks:
        print("(no tasks)")
        return 0
    print(f"{'id':<38} {'status':<12} {'type':<20} {'agent':<22} updated_at")
    print("-" * 110)
    for t in tasks:
        print(
            f"{str(t.id):<38} "
            f"{t.status.value:<12} "
            f"{t.type.value:<20} "
            f"{(t.assigned_agent or '-'):<22} "
            f"{t.updated_at.isoformat()}"
        )
    return 0


async def cmd_status(args) -> int:
    orchestrator = TaskOrchestrator()
    task = await orchestrator.get(UUID(args.task_id))
    if task is None:
        print(f"Task {args.task_id} not found")
        return 1
    _print_task(task)
    return 0


async def cmd_history(args) -> int:
    async with get_session_factory()() as session:
        repo = TaskRepository(session)
        events = await repo.list_events(UUID(args.task_id))
    if not events:
        print(f"No events for task {args.task_id}")
        return 1
    print(f"Event history for {args.task_id}:\n")
    for ev in events:
        ts = ev.created_at.isoformat()
        payload = json.dumps(ev.payload) if ev.payload else ""
        print(f"  {ts}  {ev.event_type:<20} {payload}")
    return 0


def _build_task(args) -> Task | None:
    if args.type == "employee":
        if not args.question:
            print("ERROR: --type employee requires QUESTION", file=sys.stderr)
            return None
        return Task(
            type=TaskType.EMPLOYEE_QUESTION,
            input=EmployeeQuestionInput(question=args.question),
        )
    if args.type == "customer":
        if not args.subject or not args.body:
            print("ERROR: --type customer requires --subject and --body", file=sys.stderr)
            return None
        return Task(
            type=TaskType.CUSTOMER_SUPPORT,
            input=CustomerSupportInput(
                ticket_subject=args.subject,
                ticket_body=args.body,
            ),
        )
    if args.type == "ops":
        if args.transcript_file:
            transcript = Path(args.transcript_file).read_text(encoding="utf-8")
        elif args.transcript:
            transcript = args.transcript
        else:
            print("ERROR: --type ops requires --transcript-file or --transcript", file=sys.stderr)
            return None
        return Task(
            type=TaskType.OPS_WORKFLOW,
            input=OpsWorkflowInput(
                transcript=transcript,
                meeting_title=args.title,
                attendees=args.attendees.split(",") if args.attendees else [],
            ),
        )
    return None


def main() -> int:
    telemetry.init()

    parser = argparse.ArgumentParser(description="Pollux orchestrator CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="Create database tables if not present.")

    p_submit = sub.add_parser("submit", help="Submit a task and wait for completion.")
    p_submit.add_argument(
        "--type", required=True, choices=["employee", "customer", "ops"]
    )
    p_submit.add_argument("question", nargs="?")
    p_submit.add_argument("--subject", default=None)
    p_submit.add_argument("--body", default=None)
    p_submit.add_argument("--transcript-file", default=None)
    p_submit.add_argument("--transcript", default=None)
    p_submit.add_argument("--title", default="Untitled meeting")
    p_submit.add_argument("--attendees", default="")

    p_list = sub.add_parser("list", help="List recent tasks.")
    p_list.add_argument(
        "--status",
        choices=[s.value for s in TaskStatus],
        default=None,
    )
    p_list.add_argument("--limit", type=int, default=20)

    p_status = sub.add_parser("status", help="Get a task's current state.")
    p_status.add_argument("task_id")

    p_history = sub.add_parser("history", help="Show a task's event log.")
    p_history.add_argument("task_id")

    args = parser.parse_args()

    handlers = {
        "migrate": cmd_migrate,
        "submit": cmd_submit,
        "list": cmd_list,
        "status": cmd_status,
        "history": cmd_history,
    }
    return asyncio.run(handlers[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())

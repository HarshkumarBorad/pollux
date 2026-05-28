"""CLI for testing individual agents standalone, plus the full pipeline.

Each specialist subcommand bypasses routing for isolated testing. The
`task` subcommand runs the end-to-end Coordinator → Specialist → Escalation
flow — what production traffic actually exercises.

Usage:
    python -m agents.cli list
    python -m agents.cli hr "What is the leave policy?"
    python -m agents.cli it "How do I authenticate API requests?"
    python -m agents.cli customer --subject "Cannot log in" --body "..."
    python -m agents.cli ops --transcript-file ./meeting.txt

    :: Full pipeline (Coordinator → Specialist → Escalation):
    python -m agents.cli task --type employee "What's the leave policy?"
    python -m agents.cli task --type customer --subject "..." --body "..."
    python -m agents.cli task --type ops --transcript-file ./meeting.txt
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from core import telemetry
from core.tasks import (
    CustomerSupportInput,
    EmployeeQuestionInput,
    OpsWorkflowInput,
    Task,
    TaskType,
)

from agents import get_agent, list_agent_cards, run_task


def _print_task_result(result) -> None:
    print("\n" + "=" * 72)
    print(result.summary)
    print("=" * 72)
    if result.citations:
        print("\nCitations:")
        for i, c in enumerate(result.citations, 1):
            score = f" (score={c.score:.2f})" if c.score is not None else ""
            domain = f" [{c.domain}]" if c.domain else ""
            print(f"  [{i}]{domain} {c.source}{score}")
    if result.artifacts:
        print("\nArtifacts:")
        print(json.dumps(result.artifacts, indent=2, default=str)[:2000])
    if result.confidence is not None:
        print(f"\nConfidence: {result.confidence:.2f}")


def _print_final_task(task: Task) -> None:
    print("\n" + "─" * 72)
    print(f"Final status   : {task.status.value}")
    print(f"Routed to      : {task.assigned_agent}")
    if task.error:
        print(f"Error          : {task.error}")
    print("─" * 72)
    if task.result is not None:
        _print_task_result(task.result)


async def cmd_list(_args) -> int:
    cards = list_agent_cards()
    print(f"Registered agents ({len(cards)}):\n")
    from agents import AGENT_REGISTRY

    for card in cards:
        cls = AGENT_REGISTRY.get(card.id)
        domain_suffix = f"  [domain={cls.domain.value}]" if cls and cls.domain else ""
        print(f"  {card.id:<22} {card.name}{domain_suffix}")
        print(f"  {'':<22} {card.description}")
        for cap in card.capabilities:
            print(f"  {'':<22}   • {cap.name}: {cap.description}")
        print()
    return 0


async def cmd_hr(args) -> int:
    agent = get_agent("hr_specialist")
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question=args.question),
    )
    result = await agent.run(task)
    _print_task_result(result)
    return 0


async def cmd_it(args) -> int:
    agent = get_agent("it_specialist")
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question=args.question),
    )
    result = await agent.run(task)
    _print_task_result(result)
    return 0


async def cmd_customer(args) -> int:
    agent = get_agent("customer_facing")
    task = Task(
        type=TaskType.CUSTOMER_SUPPORT,
        input=CustomerSupportInput(
            ticket_subject=args.subject,
            ticket_body=args.body,
        ),
    )
    result = await agent.run(task)
    _print_task_result(result)
    return 0


async def cmd_ops(args) -> int:
    transcript = _resolve_transcript(args)
    if transcript is None:
        return 1
    agent = get_agent("ops_planner")
    task = Task(
        type=TaskType.OPS_WORKFLOW,
        input=OpsWorkflowInput(
            transcript=transcript,
            meeting_title=args.title,
            attendees=args.attendees.split(",") if args.attendees else [],
        ),
    )
    result = await agent.run(task)
    _print_task_result(result)
    return 0


async def cmd_task(args) -> int:
    """End-to-end: Coordinator → Specialist → Escalation."""
    if args.type == "employee":
        if not args.question:
            print("ERROR: --type employee requires QUESTION positional arg.", file=sys.stderr)
            return 1
        task = Task(
            type=TaskType.EMPLOYEE_QUESTION,
            input=EmployeeQuestionInput(question=args.question),
        )
    elif args.type == "customer":
        if not args.subject or not args.body:
            print("ERROR: --type customer requires --subject and --body.", file=sys.stderr)
            return 1
        task = Task(
            type=TaskType.CUSTOMER_SUPPORT,
            input=CustomerSupportInput(
                ticket_subject=args.subject,
                ticket_body=args.body,
            ),
        )
    elif args.type == "ops":
        transcript = _resolve_transcript(args)
        if transcript is None:
            return 1
        task = Task(
            type=TaskType.OPS_WORKFLOW,
            input=OpsWorkflowInput(
                transcript=transcript,
                meeting_title=args.title,
                attendees=args.attendees.split(",") if args.attendees else [],
            ),
        )
    else:
        print(f"ERROR: unknown --type {args.type!r}", file=sys.stderr)
        return 1

    final = await run_task(task)
    _print_final_task(final)
    return 0 if final.status.value in {"completed", "escalated"} else 1


def _resolve_transcript(args) -> str | None:
    if args.transcript_file:
        return Path(args.transcript_file).read_text(encoding="utf-8")
    if args.transcript:
        return args.transcript
    print("ERROR: provide --transcript-file or --transcript", file=sys.stderr)
    return None


def main() -> int:
    telemetry.init()

    parser = argparse.ArgumentParser(description="Run a Pollux agent or the full pipeline.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all registered agents and capabilities.")

    p_hr = sub.add_parser("hr", help="Run the HR Specialist (bypasses routing).")
    p_hr.add_argument("question")

    p_it = sub.add_parser("it", help="Run the IT/Tech Specialist (bypasses routing).")
    p_it.add_argument("question")

    p_customer = sub.add_parser("customer", help="Run the Customer-Facing Specialist.")
    p_customer.add_argument("--subject", required=True)
    p_customer.add_argument("--body", required=True)

    p_ops = sub.add_parser("ops", help="Run the Ops Planner.")
    p_ops.add_argument("--transcript-file", default=None)
    p_ops.add_argument("--transcript", default=None)
    p_ops.add_argument("--title", default="Untitled meeting")
    p_ops.add_argument("--attendees", default="", help="Comma-separated attendees.")

    p_task = sub.add_parser(
        "task",
        help="Run the full pipeline: Coordinator routes → Specialist processes → Escalation reviews.",
    )
    p_task.add_argument(
        "--type",
        required=True,
        choices=["employee", "customer", "ops"],
        help="Task type to construct.",
    )
    # --type employee
    p_task.add_argument("question", nargs="?", help="Question text (for --type employee).")
    # --type customer
    p_task.add_argument("--subject", default=None)
    p_task.add_argument("--body", default=None)
    # --type ops
    p_task.add_argument("--transcript-file", default=None)
    p_task.add_argument("--transcript", default=None)
    p_task.add_argument("--title", default="Untitled meeting")
    p_task.add_argument("--attendees", default="", help="Comma-separated attendees.")

    args = parser.parse_args()

    handlers = {
        "list": cmd_list,
        "hr": cmd_hr,
        "it": cmd_it,
        "customer": cmd_customer,
        "ops": cmd_ops,
        "task": cmd_task,
    }
    return asyncio.run(handlers[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())

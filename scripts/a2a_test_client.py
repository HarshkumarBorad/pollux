"""Minimal A2A test client for Pollux's a2a_variant server.

Used in place of the (removed-from-modern-a2a-sdk) `a2a-cli`. Resolves
the Agent Card at the given URL, builds an SDK client for it, sends a
single message, and prints the agent's text response.

Usage examples:

    :: Specialist endpoints expect their respective input shapes
    python scripts/a2a_test_client.py http://127.0.0.1:8003/agents/hr_specialist/ \
        "What is the leave policy?"

    python scripts/a2a_test_client.py http://127.0.0.1:8003/agents/it_specialist/ \
        "How do I authenticate API requests?"

    :: Coordinator runs the FULL pipeline (Coordinator -> Specialist -> Escalation)
    python scripts/a2a_test_client.py http://127.0.0.1:8003/agents/coordinator/ \
        "What is the leave policy?"

The script keeps things deliberately minimal — no streaming visualization,
no auth, no retries. Real production clients use a2a.client.ClientFactory
directly. This is a portfolio-friendly "it works end-to-end" smoke test.
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from a2a.client import ClientConfig, ClientFactory
from a2a.helpers.proto_helpers import (
    get_artifact_text,
    get_message_text,
    new_text_message,
)
from a2a.types import Role, SendMessageRequest


async def main(agent_url: str, question: str) -> int:
    # Use a generous timeout — the full pipeline (HF embed + chat + DB) can
    # take 15-30 seconds on cold start.
    async with httpx.AsyncClient(timeout=180.0) as http_client:
        config = ClientConfig(
            httpx_client=http_client,
            streaming=True,   # let the server stream events; we'll aggregate
            polling=False,
        )
        factory = ClientFactory(config=config)

        # `create_from_url` fetches /.well-known/agent-card.json and picks
        # the best supported transport (JSON-RPC for our server).
        try:
            client = await factory.create_from_url(agent_url)
        except Exception as exc:
            print(f"ERROR: Could not resolve A2A agent at {agent_url}: {exc}", file=sys.stderr)
            return 1

        message = new_text_message(question, role=Role.ROLE_USER)
        request = SendMessageRequest(message=message)

        print(f"=> {agent_url}\n=> {question}\n")
        print("=" * 72)

        try:
            async for event in client.send_message(request):
                # event is a `StreamResponse` proto containing one of:
                # message / task / status_update / artifact_update.
                text = ""
                if event.HasField("message"):
                    text = get_message_text(event.message)
                elif event.HasField("task"):
                    # Task contains artifacts; pull text from each.
                    chunks = [get_artifact_text(a) for a in event.task.artifacts]
                    text = "\n".join(c for c in chunks if c)
                elif event.HasField("status_update"):
                    if event.status_update.status.HasField("message"):
                        text = get_message_text(event.status_update.status.message)
                elif event.HasField("artifact_update"):
                    text = get_artifact_text(event.artifact_update.artifact)
                if text:
                    print(text)
        except Exception as exc:
            print(f"\nERROR while streaming: {exc}", file=sys.stderr)
            return 2
        finally:
            await client.close()

        print("=" * 72)
    return 0


def cli() -> int:
    if len(sys.argv) < 3:
        print(
            "Usage: python scripts/a2a_test_client.py <agent-url> <question>\n"
            "Example:\n"
            "  python scripts/a2a_test_client.py "
            "http://127.0.0.1:8003/agents/hr_specialist/ \"What is the leave policy?\"",
            file=sys.stderr,
        )
        return 1
    return asyncio.run(main(sys.argv[1], " ".join(sys.argv[2:])))


if __name__ == "__main__":
    sys.exit(cli())

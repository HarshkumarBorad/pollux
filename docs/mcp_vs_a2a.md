# MCP vs A2A — when to use which

Pollux exposes the **same agent roster** through two completely different
inter-agent transports: Anthropic's **Model Context Protocol (MCP)** and
Google's **Agent-to-Agent (A2A)**. They solve overlapping problems with
different design philosophies. This doc compares them and explains how
Pollux uses each.

> TL;DR: MCP optimizes for "an LLM client picks a tool." A2A optimizes
> for "agents talk to other agents as peers." Different problems, both
> valid. Pollux ships both because the agent business logic doesn't care
> which one you choose — only the transport layer does.

---

## At a glance

|                              | **MCP** (Anthropic) | **A2A** (Google) |
|------------------------------|---|---|
| **Design philosophy**        | LLM-as-client picks tools | Peer-to-peer agent-to-agent calls |
| **Discovery**                | One server lists all tools | Each agent has its own Agent Card at `.well-known/agent-card.json` |
| **Transport**                | JSON-RPC over stdio or HTTP+SSE | HTTP + Server-Sent Events with JSON-RPC dispatching |
| **Wire format**              | Tools (function-call style) | Tasks with state machine (`SUBMITTED` → `WORKING` → `COMPLETED`/`FAILED`/`CANCELED`) |
| **Streaming**                | Tool-result streaming via SSE | First-class — Task events stream as `Message` / `TaskStatusUpdate` / `TaskArtifactUpdate` |
| **Identity / auth**          | Server-level (trust the MCP server) | Per-agent — Agent Cards can carry auth metadata, the SDK has `AuthInterceptor` |
| **State persistence**        | Stateless tool calls | Tasks have IDs + history, persisted by the server |
| **Cancellation**             | No protocol primitive | `CancelTaskRequest` is part of the spec |
| **Multi-tenancy**            | Server-level | `tenant` field in `AgentInterface` |
| **Where it shines**          | LLM clients (Claude Desktop, Cline, Cursor) calling external tools | Agent meshes — your coordinator agent calling specialist agents that may live in different processes / orgs |
| **Where it struggles**       | Long-running multi-step tasks (no native task state) | Lightweight one-shot tool calls (heavier protocol envelope) |
| **Pollux deployment**        | One `FastMCP` server, ten tools at `/mcp` | One `Starlette` app, five A2A endpoints — each at `/agents/<id>/` with its own Agent Card |

---

## How Pollux uses each

### MCP variant

```
Claude Desktop (or Cline / Cursor) ──stdio JSON-RPC──▶ FastMCP server
                                                      └─ 10 @mcp.tool() functions
                                                         ├─ submit_employee_question
                                                         ├─ submit_customer_ticket
                                                         ├─ submit_ops_workflow
                                                         ├─ query_hr, query_it
                                                         ├─ draft_customer_reply
                                                         ├─ plan_from_meeting
                                                         ├─ list_agents
                                                         ├─ get_task_status
                                                         └─ list_tasks
```

The MCP variant is "Pollux as a toolbox for an LLM client." Claude Desktop
sees the ten tools, picks the right one for the user's question, calls it,
displays the result inline. The protocol is well-suited for that flow:

- **Tool discovery is server-wide** (`tools/list`) — the client gets all
  ten in one call.
- **Each tool call is a complete unit** — no task state to manage between
  calls.
- **Server-pushed events stream back** — when the Coordinator routes via
  `submit_employee_question`, the client sees progress events via SSE.

The MCP variant runs in two transports: **stdio** (used by Claude Desktop
and most local MCP clients) and **Streamable HTTP** (used by remote
agents). One source of truth, two transports.

### A2A variant

```
Coordinator client ──HTTP JSON-RPC──▶ /agents/hr_specialist/
                                       └─ AgentCard at /.well-known/agent-card.json
                                          • supported_interfaces: [JSONRPC 1.0]
                                          • capabilities: [streaming]
                                          • skills: [answer_hr_question]

(Same client also opens connections to it_specialist, customer_facing,
 ops_planner, and coordinator — each at its own URL with its own card.)
```

The A2A variant is "Pollux as a federation of independent agents." Each
agent is its own HTTP endpoint with its own Agent Card. A coordinator
client (could be another Pollux Coordinator agent, or any other A2A peer)
discovers them, picks one, and submits a Task. The protocol is well-suited
for that flow:

- **Per-agent identity** — each Agent Card can carry its own auth, its own
  versioned protocol_binding, its own supported MIME types.
- **Tasks have explicit state** — the protocol's `TaskState` enum tracks
  `SUBMITTED → WORKING → COMPLETED / FAILED / CANCELED`, and clients can
  resubscribe to a task by ID.
- **First-class streaming** — events arrive as a typed `StreamResponse`
  union (`Message` / `Task` / `TaskStatusUpdate` / `TaskArtifactUpdate`),
  not raw text chunks.

In Pollux's specific layout, all five agents happen to live in the same
process — but the protocol doesn't know that. A real deploy could split
each agent into a separate container, scale them independently, run them
on different machines, or hand off ownership to a different team — and the
clients wouldn't have to change.

---

## When to use which

### Pick MCP when…
- Your client is an LLM IDE / chat app (Claude Desktop, Cline, Cursor).
- You want one server to publish many tools the LLM can mix-and-match.
- Your interactions are short-lived: invoke tool → get result → continue
  the conversation.
- You want to integrate with the broader MCP ecosystem (the registry,
  marketplaces, etc.).

### Pick A2A when…
- Your client is itself an agent that needs to delegate to peer agents.
- Your tasks are long-running and benefit from explicit state + resubscribe.
- You want per-agent identity, auth, or independent deployment.
- You're building a federated mesh where different orgs run different
  agents.

### Pick **both** (the Pollux approach) when…
- You want to ship one set of agent business logic.
- You want LLM clients to consume it via MCP.
- You want agent meshes to consume it via A2A.
- You want a comparison artifact for your portfolio — like this doc.

The mental model: **business logic is protocol-neutral**. The
specialist agents, the orchestrator, the knowledge layer, the database
schema — none of them know which transport surfaced the request. Adding
a third transport (gRPC, JSON over WebSocket, whatever) is a new
`pollux/<variant>/` package and zero changes everywhere else.

---

## Implementation receipts

The two variant directories are deliberately the same shape:

```
mcp_variant/                          a2a_variant/
├── __init__.py                       ├── __init__.py
├── server.py     ◀─ entry point      ├── server.py     ◀─ entry point
└── tools.py      ◀─ tool decorators  ├── cards.py      ◀─ AgentCard builders
                                      └── executor.py   ◀─ AgentExecutor impl
```

Both `server.py` files run a similar prelude:

1. Initialize telemetry.
2. Idempotently run DB migrations.
3. Build the transport-specific server.
4. Mount the agent roster from `AGENT_REGISTRY` (the same registry both
   variants read from).
5. Hand off to uvicorn (or stdio for MCP).

The interesting comparison happens at the call sites:

### MCP — tool decorator

```python
@mcp.tool()
async def submit_employee_question(question: str) -> dict:
    """Submit an employee question to Pollux."""
    task = Task(
        type=TaskType.EMPLOYEE_QUESTION,
        input=EmployeeQuestionInput(question=question),
    )
    final = await TaskOrchestrator().submit(task)
    return _task_to_dict(final)
```

The MCP runtime sees the type hints, generates a JSON Schema, advertises
the tool in `tools/list`, and dispatches calls based on the tool name.
Tool docstrings double as descriptions the LLM client uses to decide
which tool to call.

### A2A — agent executor

```python
class PolluxAgentExecutor(AgentExecutor):
    def __init__(self, agent: BaseAgent):
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        input_data = _extract_input(context)
        task = _build_task_for_type(self.agent.supported_task_types[0], input_data)
        result = await self.agent.run(task)
        await event_queue.enqueue_event(new_text_message(result.summary))
```

The A2A runtime takes care of: parsing the JSON-RPC envelope, building
the `RequestContext` (with the incoming `Message`, task ids, server
context), invoking `execute()`, managing the `EventQueue`, and persisting
the task state. Your executor just bridges between A2A types and the
Pollux types.

---

## A note on protocol evolution

Both protocols are young (MCP shipped Nov 2024, A2A shipped Apr 2025) and
actively evolving:

- **MCP** had a major transport shift mid-2025 from the old SSE-based
  HTTP transport to the current "Streamable HTTP" (which uses negotiated
  Accept headers). Older clients still work but the new transport is
  preferred.
- **A2A** is mid-migration from a pydantic-based wire format to a
  protobuf-based one in the `a2a-sdk` Python library. The new API has
  `AgentCard.supported_interfaces` instead of a top-level `url` field,
  and uses `create_jsonrpc_routes()` + `create_agent_card_routes()`
  instead of `A2AStarletteApplication`.

The protocols are stable enough to build on, but pin your SDK versions
carefully and re-test on minor bumps. Pollux's `a2a_variant` had to be
rewritten once between the initial commit and final polish — a worthwhile
reminder that "pin to a snapshot" beats "track latest" for portfolio work.

---

## Further reading

- MCP spec: <https://modelcontextprotocol.io>
- A2A spec: <https://google.github.io/A2A>
- FastMCP: <https://gofastmcp.com>
- a2a-sdk: <https://github.com/google/a2a-python>
- Pollux MCP variant code: [`mcp_variant/`](../mcp_variant/)
- Pollux A2A variant code: [`a2a_variant/`](../a2a_variant/)

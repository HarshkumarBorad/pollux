# 🌟 Pollux — Multi-Agent System for Organizational Automation

Six domain-specialist agents working together to automate **customer support**,
**internal employee Q&A**, and **operations workflows** (meeting → action items).
The same agent roster runs under **two interchangeable orchestration protocols** —
Anthropic's MCP and Google's A2A — picked via a single env var.

> Built end-to-end as a portfolio project. Sibling to
> [DocuMind](https://github.com/HarshkumarBorad/documind). Phase-by-phase build,
> production-ready target.

---

## 🤖 Agent roster

| Agent | Role |
|---|---|
| 🧭 **Coordinator** | Entry point — classifies intent, plans response, dispatches to specialist |
| 🧑‍💼 **HR Specialist** | Answers HR / policy / onboarding questions |
| 🔧 **IT/Tech Specialist** | Answers IT / SDK / technical questions |
| 📦 **Customer-Facing Specialist** | Drafts external-facing replies (tone-shifted) |
| 📋 **Ops Planner** | Decomposes multi-step requests (e.g. meeting → tasks) |
| 🚨 **Escalation / QA** | Confidence scoring + human handoff |

## 🔄 The two orchestration variants

| Aspect | **MCP** | **A2A** |
|---|---|---|
| Protocol | Anthropic Model Context Protocol | Google Agent-to-Agent |
| Discovery | MCP server lists tools | Agent Card registry per agent |
| Communication | Synchronous JSON-RPC tool calls | Async Tasks with state machine + streaming |
| Identity | Server-side trust | Agent-level identity, JWT/OAuth built in |
| Best for | LLM-as-client picking tools | True peer-to-peer agent meshes |

Both variants share the **entire agent business logic, knowledge layer, LLM
client, UI, and REST API**. Only the inter-agent transport differs. Pick at
startup via `POLLUX_ORCHESTRATION=mcp` or `=a2a`.

## 🧭 Build phases

- [x] **Phase 1** — Project scaffold + core models
- [x] **Phase 2** — Standalone knowledge layer (ChromaDB + BGE-M3)
- [x] **Phase 3** — Agent abstraction + four specialist agents
- [x] **Phase 4** — Coordinator + Escalation
- [x] **Phase 5** — Task orchestrator + SQLite persistence
- [x] **Phase 6** — MCP variant
- [x] **Phase 7** — A2A variant
- [ ] **Phase 8** — REST API + WebSocket streaming
- [ ] **Phase 9** — Streamlit UI (chat / ticket inbox / ops workflows / agent log)
- [ ] **Phase 10** — Observability, deployment, demo polish

## 🚀 Phase 1 quickstart

Prereqs: Python 3.11+ and Docker.

```cmd
:: 1. Configure
copy .env.example .env
::    Set HF_TOKEN at minimum. OPENAI_API_KEY is optional.

:: 2. Install lightweight deps (Phase 1 only needs core libs)
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip      :: pip <23 trips on prebuilt wheels for greenlet/lxml on Windows
pip install -r requirements.txt

:: 3. Run the smoketest — verifies imports, model round-trips, and telemetry
python -m core.smoketest
```

You should see structured log lines confirming the three sample task types
serialize / deserialize cleanly and an OpenTelemetry span dump to stdout.

Or via Docker:

```cmd
docker compose build core
docker compose run --rm core
```

### Phase 2 — try the knowledge layer

The knowledge layer is one shared ChromaDB collection with **per-chunk
domain metadata** — agents filter by domain at query time rather than
hitting separate collections. Embedded by default (no Chroma service to
run); switch to HTTP mode via env when you want a split deploy.

```cmd
:: Drop documents into a domain's folder
mkdir data\knowledge\hr
copy somefile.pdf data\knowledge\hr\

:: Ingest (idempotent — content-hashed chunk IDs upsert in place)
python -m core.knowledge.cli ingest --domain hr --path .\data\knowledge\hr

:: Test query
python -m core.knowledge.cli query "What is the leave policy?" --domain hr

:: See chunk counts
python -m core.knowledge.cli count

:: Wipe a domain and re-ingest
python -m core.knowledge.cli reset --domain hr
```

Domains: `hr` / `it` / `product` / `general`. The first three are the
knowledge slices owned by the HR / IT / Customer-Facing specialist
agents. `general` is the catch-all for cross-domain or uncategorized docs.

### Phase 3 — try the specialist agents

Four agents wired up, each with its own LangGraph state machine. Test any
of them standalone (the Coordinator that routes between them lands in
Phase 4):

```cmd
:: List the agent roster + capabilities
python -m agents.cli list

:: HR knowledge Q&A
python -m agents.cli hr "What is the leave policy?"

:: IT/SDK Q&A
python -m agents.cli it "Which Python version is required for the SDK?"

:: Customer-facing reply (two-stage: internal draft -> tone-shifted rewrite)
python -m agents.cli customer ^
    --subject "API key not working" ^
    --body "I rotated my key yesterday and now get 401s on every call."

:: Ops planner (decompose a meeting transcript into action items)
python -m agents.cli ops --transcript-file .\meeting.txt ^
    --title "Platform weekly" ^
    --attendees "Lina,Marc"
```

Each agent's pipeline:

| Agent | Graph | LLM calls |
|---|---|---|
| `hr_specialist` | retrieve → synthesize | HF chat × 1 |
| `it_specialist` | retrieve → synthesize | HF chat × 1 |
| `customer_facing` | retrieve → draft → rewrite | HF chat × 2 |
| `ops_planner` | summarize → plan (JSON) | HF chat × 2 |

Specialists stay on HF Inference deliberately — the "works without OpenAI"
story is part of the demo. The Coordinator and Ops Planner upgrade to
OpenAI when `OPENAI_API_KEY` is set (see Phase 4).

### Phase 4 — Coordinator + Escalation (the full pipeline)

Six agents now wired together. The Coordinator routes; the specialist
processes; the Escalation/QA agent reviews. Run the whole thing end-to-end:

```cmd
:: Employee question — Coordinator's LLM picks HR vs IT
python -m agents.cli task --type employee "What's the leave policy?"

:: Customer ticket — rule-routes to customer_facing
python -m agents.cli task --type customer ^
    --subject "API key not working" ^
    --body "I rotated my key yesterday and now get 401s."

:: Meeting transcript — rule-routes to ops_planner
python -m agents.cli task --type ops --transcript-file meeting.txt
```

Pipeline shape:

```
       ┌─────────────────────────────┐
       │  Task arrives (from REST)   │
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │      Coordinator            │      ← OpenAI if OPENAI_API_KEY set,
       │   classifies + routes       │        else HF. Rule-based shortcuts
       └──────────────┬──────────────┘        for CUSTOMER_SUPPORT / OPS_WORKFLOW.
                      ▼
       ┌─────────────────────────────┐
       │  HR | IT | CustomerFacing   │      ← HF Inference only (specialists
       │  | OpsPlanner               │        stay on HF deliberately).
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │     Escalation / QA         │      ← Rule-based verdict in Phase 4.
       │  ship | revise | escalate   │        LLM-judge optional in Phase 10.
       └──────────────┬──────────────┘
                      ▼
              status = completed
                or escalated
```

| Verdict | When | Final status |
|---|---|---|
| `ship` | Specialist confidence ≥ 0.7, no no-info marker | `COMPLETED` |
| `revise` | Confidence 0.4 – 0.7 (grey zone) | `ESCALATED` (Phase 4 collapses revise → escalate; Phase 5 may loop) |
| `escalate` | Confidence < 0.4 **OR** no-info marker **OR** task error | `ESCALATED` |

**OpenAI fallback flag.** Set `OPENAI_API_KEY=sk-...` in `.env` and the
Coordinator + OpsPlanner auto-upgrade. Everything else stays on HF — that
keeps `OPENAI_API_KEY` purely additive, not required.

### Phase 5 — orchestrator + persistence

Phase 4's in-memory `run_task()` is now wrapped by `TaskOrchestrator`,
which adds **SQLite-backed persistence**, **retries on transient
failures**, **per-task timeouts**, and a **"revise" loop** (one extra run
when Escalation's verdict is `revise` before collapsing to `escalated`).

```cmd
:: One-time DB setup
python -m orchestrator.cli migrate

:: Submit a task — orchestrator persists it, runs the pipeline, persists
:: every status transition, and returns the final task.
python -m orchestrator.cli submit --type employee "What's the leave policy?"

:: Browse the task store
python -m orchestrator.cli list                          :: most recent 20
python -m orchestrator.cli list --status escalated       :: filter
python -m orchestrator.cli status <task-id>              :: current state
python -m orchestrator.cli history <task-id>             :: event log
```

Default DB is `sqlite+aiosqlite:///pollux.db` (created in the repo root).
Swap to Postgres for production by setting `DATABASE_URL=postgresql+asyncpg://...`
in `.env` — same schema works in both, no Alembic needed for the demo (Phase 10
may add migrations once the schema starts evolving).

**Two submit modes:**
- `orchestrator.submit(task)` — block until the pipeline finishes. Used by
  the CLI and Phase 8's sync REST endpoints.
- `orchestrator.submit_async(task)` — persist + return immediately;
  background asyncio task drives the pipeline. Used by Phase 8's async
  REST endpoint pattern (`POST /tasks` returns 202, client polls
  `GET /tasks/{id}` for progress).

**Knobs** (`TaskOrchestrator` constructor):
- `timeout=180` — per-attempt timeout in seconds
- `max_retries=2` — transient-error retries before marking FAILED
- `revise_attempts=1` — how many times Escalation's `revise` verdict
  triggers a fresh run

Schema is two tables, both queryable directly:
- `tasks` — current state of each task (indexed `status`, `assigned_agent`,
  `updated_at`); full pydantic Task snapshot lives in `payload_json`.
- `task_events` — append-only timeline (`submitted` → `routed` → `done`,
  or `retry_timeout` / `retry_error` / `revise_retry` on the unhappy path).
  Powers the per-task history view in the Phase 9 UI.

### Phase 6 — MCP variant (10 tools)

The full Pollux system is now reachable as an **MCP server**. Run it locally
and connect Claude Desktop / Cline / Cursor / any MCP client. Same agent
business logic as the orchestrator CLI — just a different transport.

```cmd
:: Stdio mode (used by Claude Desktop and friends)
python -m mcp_variant.server

:: Streamable HTTP for remote MCP clients
python -m mcp_variant.server --transport http --port 8002
```

**Tools exposed:**

| Tool | Category | What it does |
|---|---|---|
| `submit_employee_question` | submit | Full pipeline; Coordinator routes HR vs IT, Escalation reviews, persisted |
| `submit_customer_ticket` | submit | Full pipeline for support tickets; two-stage tone-shifted reply |
| `submit_ops_workflow` | submit | Full pipeline for meeting transcripts → structured action items |
| `query_hr` | direct | HR Specialist only; no Coordinator, no DB, no QA |
| `query_it` | direct | IT Specialist only |
| `draft_customer_reply` | direct | Customer-Facing Specialist only |
| `plan_from_meeting` | direct | Ops Planner only |
| `list_agents` | discovery | All six AgentCards with capabilities |
| `get_task_status` | inspection | Look up a task by ID |
| `list_tasks` | inspection | Recent submissions, optionally filtered by status |

**Wire it into Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pollux": {
      "command": "python",
      "args": ["-m", "mcp_variant.server"],
      "cwd": "/absolute/path/to/pollux"
    }
  }
}
```

Restart Claude Desktop — tools appear in the picker. Ask:
*"Use pollux to draft a customer reply for ticket #4711…"* and Claude picks
`submit_customer_ticket`, sees the routing decision, the two-stage draft,
the QA verdict, all in one tool call.

The MCP server idempotently runs the DB migration on startup, so a fresh
clone works with a single command (no `python -m core.db.migrate create`
step needed).

### Phase 7 — A2A variant (5 agent endpoints + discovery)

The same Pollux agent roster is also reachable via Google's **Agent-to-Agent
(A2A)** protocol. Each agent has its own HTTP endpoint and Agent Card —
peer-to-peer agent communication instead of MCP's LLM-as-client pattern.

```cmd
:: Start the A2A server (idempotently creates DB tables, mounts all agents)
python -m a2a_variant.server --host 127.0.0.1 --port 8003
```

**Discovery — list every mounted agent:**

```cmd
curl http://127.0.0.1:8003/
```

Returns:

```json
{
  "name": "Pollux A2A Server",
  "agents": [
    {"id": "coordinator", "url": "http://127.0.0.1:8003/agents/coordinator", ...},
    {"id": "hr_specialist", ...},
    ...
  ]
}
```

**Each agent publishes its own Agent Card** at the standard well-known path:

```cmd
curl http://127.0.0.1:8003/agents/hr_specialist/.well-known/agent-card.json
```

| Endpoint | Behavior |
|---|---|
| `/agents/coordinator` | **Full pipeline** — Coordinator → Specialist → Escalation, persisted to the same SQLite store the MCP variant uses |
| `/agents/hr_specialist` | Direct HR Q&A (no orchestrator, no persistence) |
| `/agents/it_specialist` | Direct IT Q&A |
| `/agents/customer_facing` | Direct two-stage ticket reply |
| `/agents/ops_planner` | Direct transcript → action items |

The Escalation agent is **not** mounted — it's a meta-agent (reviews other
agents' output, doesn't accept tasks of its own).

**Input shape.** The executor accepts an A2A `DataPart` with a JSON object —
or a `TextPart` with JSON inside — or a raw `TextPart` (treated as
`{"text": "..."}`):

| Agent | Expected JSON shape |
|---|---|
| `hr_specialist` / `it_specialist` | `{"question": "..."}` |
| `customer_facing` | `{"subject": "...", "body": "..."}` |
| `ops_planner` | `{"transcript": "...", "meeting_title": "...", "attendees": [...]}` |
| `coordinator` | Any of the above — Coordinator infers the task type from the shape |

**Streaming.** A2A's streaming envelope is supported (the agent responds
inside an event queue), but Pollux currently emits the full result as a
single event after the agent finishes. True chunk-by-chunk LLM streaming
through to A2A is a Phase 10 polish item.

**Testing it end-to-end.** The modern `a2a-sdk` doesn't ship a CLI tool —
use the bundled minimal test client instead:

```cmd
:: Specialist endpoints expect their respective input shapes
python scripts/a2a_test_client.py http://127.0.0.1:8003/agents/hr_specialist/ "What is the leave policy?"

:: Coordinator runs the full pipeline (Coordinator -> Specialist -> Escalation)
python scripts/a2a_test_client.py http://127.0.0.1:8003/agents/coordinator/ "What is the leave policy?"
```

The script resolves the Agent Card, picks JSON-RPC, sends the question,
and streams back the response. Requires `HF_TOKEN` set + (for meaningful
HR answers) docs ingested into `data/knowledge/hr/`.

### MCP vs A2A — when to use which

Same agent business logic powers both variants; only the inter-agent
transport differs. Phase 10 will ship a dedicated `docs/mcp_vs_a2a.md`
comparison; the short version:

| Aspect | MCP | A2A |
|---|---|---|
| Discovery | One server lists all tools | One Agent Card per agent at `.well-known/agent-card.json` |
| Communication | Synchronous JSON-RPC tool calls | Async Tasks with state machine + streaming |
| Identity | Server-side (trust the MCP server) | Per-agent (Agent Cards can carry auth metadata) |
| Best for | LLM-as-client picking tools (Claude Desktop, Cline, Cursor) | Peer-to-peer agent meshes — agents calling agents |
| Wire format | JSON-RPC over stdio or HTTP+SSE | HTTP + SSE + structured task envelope |

For Pollux, both endpoints serve the same six agents through the same
LangGraph implementations. Choose by client.

## 🛠️ Tech stack (planned — phases progressively add these)

| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph (per-agent state machines) |
| MCP variant | FastMCP |
| A2A variant | `a2a-python` (official Google SDK) |
| Knowledge | ChromaDB + BGE-M3 (standalone, no external RAG service) |
| LLM | HF Inference Providers; optional OpenAI fallback for Coordinator/Planner |
| Persistence | SQLAlchemy + aiosqlite (SQLite default, Postgres-ready) |
| API | FastAPI + Uvicorn |
| Frontend | Streamlit |
| Auth | API-key (added when needed in Phase 8) |
| Observability | OpenTelemetry traces, structlog logs, Prometheus metrics |
| Containers | Docker Compose |
| Runtime | **async throughout** — `asyncio` is the unifying primitive |

## 📂 Project structure

```
pollux/
├── docker-compose.yml          ← Phase 1: core service only
├── Dockerfile
├── .env.example
├── requirements.txt
├── README.md
├── LICENSE
│
├── core/                       ← Phase 1
│   ├── config.py               ← single Pydantic Settings model
│   ├── telemetry.py            ← structlog + OpenTelemetry
│   ├── smoketest.py            ← phase 1 verification
│   └── tasks/
│       └── models.py           ← Task / Message / Capability / AgentCard
│
├── docs/                       ← architecture diagrams + mcp_vs_a2a.md (Phase 10)
└── tests/                      ← unit + integration (Phase 10)
```

Later phases add `agents/`, `knowledge/`, `api/`, `ui/`, `mcp_variant/`,
`a2a_variant/`, `data/`, and `scripts/`.

## 📜 License

[MIT](LICENSE). Project content (sample tickets, transcripts, knowledge docs)
under `data/` will be entirely fictional once Phase 10 ships sample data.

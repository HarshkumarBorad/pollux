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
- [ ] **Phase 4** — Coordinator + Escalation
- [ ] **Phase 5** — Task orchestrator + SQLite persistence
- [ ] **Phase 6** — MCP variant
- [ ] **Phase 7** — A2A variant
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
story is part of the demo. The Coordinator and Ops Planner in Phase 4 may
optionally upgrade to OpenAI when `OPENAI_API_KEY` is set, for stronger
reasoning at the routing / planning layer.

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

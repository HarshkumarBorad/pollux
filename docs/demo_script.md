# Pollux — 3-minute live demo script

A walkthrough you can run in an interview, call, or recording. Tight,
narrated, and ordered for impact. Total time: **~3 minutes**.

The goal isn't to show every feature — it's to land **one message**:

> *Six agents collaborating through a single orchestrator, runnable under
> two interchangeable transports (MCP and A2A). Same business logic, just
> swap the wire protocol.*

---

## Pre-flight (do this 60s before the demo starts)

**If demoing on HuggingFace Spaces:**
1. Open https://huggingface.co/spaces/Harshborad/pollux — let it fully load. This wakes the container so cold-start latency doesn't hit during the demo.
2. Submit one warm-up query in **💬 Chat** (anything — *"hello"* is fine). This pre-warms the HF Inference provider for the chat model.
3. Have these two tabs ready in your browser:
   - The Space itself (Chat page open)
   - [`docs/mcp_vs_a2a.md`](mcp_vs_a2a.md) on GitHub

**If demoing locally with docker-compose** (preferred for technical audiences — shows MCP + A2A):
1. `docker compose up -d` and wait for all 5 services to become healthy
2. `docker compose exec api python scripts/ingest_samples.py`
3. Open these tabs:
   - http://localhost:8501 (Streamlit UI — Chat page)
   - http://localhost:8001/docs (Swagger API)
   - http://localhost:8003/ (A2A discovery — JSON listing the agent endpoints)
   - http://localhost:8002/mcp (MCP server — proves it's up)
   - [`docs/mcp_vs_a2a.md`](mcp_vs_a2a.md)

---

## The arc (5 beats, ~30s each)

### Beat 1 — Chat: route to HR (~30s)

**Action:** Paste *"What is the leave policy?"* into 💬 Chat. Hit Enter.

**Say:** *"This isn't one LLM call. The **Coordinator** classifies the intent, picks HR, the HR specialist retrieves from the knowledge base, then the **Escalation/QA** agent reviews the answer before it ships. Watch the pipeline panel on the right — these events are streaming over WebSocket as each agent finishes."*

**Why this beat:** Establishes that the streaming events are the system at work. Sets up the "agents-not-monolith" frame.

### Beat 2 — Chat: route to IT (~20s)

**Action:** New query — *"Which Python version is required for the SDK?"*

**Say:** *"Same Coordinator, different specialist. The Coordinator's classification is what decides — no hardcoded routing for Q&A."*

**Why this beat:** Proves the routing is real, not faked per-question.

### Beat 3 — Tickets: tone shift (~30s)

**Action:** Switch to 📦 Tickets. Submit a complaint like *"Subject: API key not working. Body: I rotated my key yesterday and now get 401s on every call."*

**Say:** *"The Customer-Facing specialist runs a two-stage pipeline — drafts an internal version with the full diagnosis, then rewrites it in the right tone for the external reply. You can see both stages."*

**Why this beat:** Shows agents do non-trivial work, not just Q&A.

### Beat 4 — Workflows: meeting → JSON (~30s)

**Action:** Switch to 📋 Workflows. Paste a short meeting transcript (have one ready in your clipboard). Submit.

**Say:** *"The Ops Planner agent decomposes free-form transcripts into structured action items — owner, deadline, dependencies. Output's machine-readable JSON, so this slots into a downstream automation."*

**Why this beat:** Demonstrates structured output / tool-use shape.

### Beat 5 — The differentiator (~30s)

**Action:** Open `docs/mcp_vs_a2a.md`. Scroll the comparison table.

**Say:** *"Here's the part that matters. Everything you just saw runs unchanged under **two different inter-agent transports** — Anthropic's MCP and Google's A2A. Same six agents, same orchestrator, same LangGraph state machines. The transport is one env var: `POLLUX_ORCHESTRATION=mcp` or `=a2a`. So if a team's already on Claude Desktop, MCP works. If they're building a peer-to-peer agent mesh, A2A works. The business logic is decoupled from the wire protocol — that's the whole point of the project."*

**If running locally:** flip to the A2A discovery tab (`http://localhost:8003/`) to show the five Agent Cards published at well-known paths, and the MCP server tab to show it responding.

**Why this beat:** This is the headline. Land it last.

---

## If they ask "what about observability / persistence / scale?"

Quick mentions in this order — don't volunteer, only if asked:

- 📜 **Agent Log** page → every task is persisted in SQLite with a full event timeline (status transitions, retries, QA verdicts).
- `http://localhost:8001/metrics` → Prometheus scrape target with auto-instrumented FastAPI + Pollux-specific task/agent counters.
- Structured logs (JSON when `LOG_FORMAT=json`), OpenTelemetry traces (stdout in dev, OTLP HTTP in prod).
- SQLite by default; flip `DATABASE_URL=postgresql+asyncpg://...` for prod. Same schema.

## If they ask "did you actually write this or did Claude / GPT?"

Honest answer: *"I designed the architecture, picked the stack, and drove the 10-phase build sequence. I used AI coding assistants for code generation inside each phase the same way I'd use an IDE — but the design decisions, the dual-transport idea, the agent roster, the phase ordering, all mine. The `docs/mcp_vs_a2a.md` write-up is mine end-to-end."*

(Adjust to your truth.)

---

## What NOT to demo

- **Don't open the Agent Log first.** It's a finisher, not an opener — it lands as "look at the audit trail" once they've seen tasks completing.
- **Don't show the Swagger UI** unless they ask about the API surface — it derails into endpoint enumeration.
- **Don't try to explain LangGraph / Pydantic / BGE-M3** — those are implementation details. The story is agents + transports.
- **Don't apologize for the cold start** — pre-warm it instead. If you have to wait, narrate the architecture while it loads.

---

## Recording a demo GIF / video instead

Same 5-beat structure, but record locally with `docker compose up -d` so the MCP + A2A endpoints are reachable. Tools:
- **OBS Studio** for full-screen capture
- **ScreenToGif** for short GIFs (Windows)
- Target: 60–90s GIF for the README, 3-min video for a portfolio page

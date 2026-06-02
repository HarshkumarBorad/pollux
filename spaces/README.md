---
title: Pollux
emoji: 🌟
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: true
license: mit
short_description: Multi-agent task automation — MCP + A2A variants
models:
  - Qwen/Qwen2.5-7B-Instruct
  - BAAI/bge-m3
tags:
  - multi-agent
  - mcp
  - a2a
  - langgraph
  - chromadb
  - huggingface
  - agents
  - retrieval-augmented-generation
---

# 🌟 Pollux

Six specialist agents — HR, IT, Customer-Facing, Ops Planner, Coordinator, Escalation/QA — collaborating through a single orchestrator. The same agent business logic is exposed via **two interchangeable inter-agent transports**: Anthropic's **MCP** and Google's **A2A**.

## 👉 Try this first

Open the **💬 Chat** tab in the sidebar and paste:

> *What is the leave policy?*

Hit Enter. Watch the right-side pipeline panel: the **Coordinator** classifies the intent, routes to the **HR Specialist**, the specialist retrieves from the pre-ingested knowledge base, the **Escalation/QA** agent reviews the answer, and you get a cited response. **This streaming flow IS the multi-agent system at work** — it's not a single LLM call.

⏱️ First request after sleep takes 30–60s (container wake + HF Inference warmup). After that it's snappy.

## More to try

| Page | Paste / do | What it demonstrates |
|---|---|---|
| 💬 **Chat** | *"Which Python version is required for the SDK?"* | Coordinator picks IT instead of HR — same agent roster, different routing |
| 📦 **Tickets** | Submit a customer complaint | Two-stage flow: internal draft → tone-shifted external reply |
| 📋 **Workflows** | Paste a meeting transcript | Ops Planner decomposes free text into structured action items (JSON) |
| 📜 **Agent Log** | — | Every task with its full event timeline (status transitions, retries, verdicts) |

## What this Space is — and isn't

This Space ships the **REST API + Streamlit UI** in a single container (embedded ChromaDB, embedded SQLite, sample knowledge auto-ingested on first boot). The **MCP** and **A2A** variants — the headline differentiator — are part of the full repo but need a multi-service deploy, so they're not here.

To see the full stack (5 services: chromadb + api + ui + mcp + a2a + Prometheus), clone the repo and run `docker compose up -d`.

> 🛠️ **Full source, MCP variant, A2A variant, docker-compose setup:** [github.com/HarshkumarBorad/pollux](https://github.com/HarshkumarBorad/pollux)
>
> 📖 **The headline doc — MCP vs A2A: when to use which:** [docs/mcp_vs_a2a.md](https://github.com/HarshkumarBorad/pollux/blob/main/docs/mcp_vs_a2a.md)

## How this Space differs from the GitHub repo

| Aspect | GitHub repo (docker-compose) | This Space |
|---|---|---|
| ChromaDB | Separate service via HTTP | Embedded (PersistentClient) |
| REST API | Port 8001, public | Port 8001, internal-only |
| Streamlit UI | Port 8501 | Port 7860 (HF Spaces standard) |
| MCP variant | Port 8002 public | Not included |
| A2A variant | Port 8003 public | Not included |

Same agents, same orchestrator, same DB schema — just collapsed into one container because HF Spaces only exposes one public port.

## Notes for visitors

- **Persistence:** the embedded SQLite + ChromaDB live in the container's writable layer. They survive sleep/wake but get wiped on rebuilds (every code push). Sample knowledge re-ingests automatically — your test tasks won't.
- **HF Inference quirks:** occasional 503s from a busy provider. Wait 30s and retry, or pick a different model from the Chat sidebar.

## Self-hosting

This Space is configured with a `HF_TOKEN` secret so visitors don't need their own. If you want to fork this and run your own Space (or contribute fixes back), see [`spaces/DEPLOY.md`](https://github.com/HarshkumarBorad/pollux/blob/main/spaces/DEPLOY.md) in the repo for the full deploy flow.

---
title: Pollux
emoji: 🌟
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: true
license: mit
short_description: Multi-agent system with two interchangeable orchestration protocols
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

Multi-agent system for organizational task automation. Six specialist agents
working together — same agent business logic exposed through **two
interchangeable inter-agent transports**: Anthropic's MCP and Google's A2A.

This Space runs Pollux's **REST API + Streamlit UI** in a single container
(embedded ChromaDB, embedded SQLite). The MCP and A2A variants are part of
the full repo but require a multi-service deploy — see the GitHub repo for
the docker-compose setup.

> 🛠️ Full source, MCP variant, A2A variant, and docker-compose setup:
> [github.com/HarshkumarBorad/pollux](https://github.com/HarshkumarBorad/pollux)
>
> 📖 The headline doc — **MCP vs A2A: when to use which** —
> [docs/mcp_vs_a2a.md](https://github.com/HarshkumarBorad/pollux/blob/main/docs/mcp_vs_a2a.md)

## Try it

The Space ships with **sample Aurora Labs knowledge** pre-ingested. From the
sidebar:

| Page | Try |
|---|---|
| 💬 **Chat** | *"What is the leave policy?"* — Coordinator routes to HR specialist |
| 💬 **Chat** | *"Which Python version is required for the SDK?"* — routes to IT |
| 📦 **Tickets** | Paste a customer complaint — get a tone-shifted draft reply |
| 📋 **Workflows** | Drop a meeting transcript — get action items as JSON |
| 📜 **Agent Log** | Inspect every task with its full event timeline |

Watch the **pipeline progress events stream live** as the Coordinator
routes → Specialist answers → Escalation/QA reviews. The flow takes
30–60s end-to-end on a free-tier HF token (HF Inference cold-starts add
latency on the first call after sleep).

## How this differs from the GitHub repo

| Aspect | GitHub repo (docker-compose) | This Space |
|---|---|---|
| ChromaDB | Separate service via HTTP | Embedded (PersistentClient) |
| REST API | Port 8001, public | Port 8001, internal-only |
| Streamlit UI | Port 8501 | Port 7860 (HF Spaces standard) |
| MCP variant | Port 8002 public | Not included |
| A2A variant | Port 8003 public | Not included |

Same agents, same orchestrator, same DB schema — just collapsed into one
container because HF Spaces only exposes one public port.

## Configuration

You'll need a HuggingFace Inference token (free tier works). Add it as a
**Space secret**:

1. Settings → **Variables and secrets** → **New secret**
2. Name: `HF_TOKEN`. Value: your token.
3. Save and restart the Space.

Optionally add `OPENAI_API_KEY` as a second secret to upgrade the
Coordinator + Ops Planner agents to GPT-4o-mini (better classification +
planning quality). Specialists stay on HF either way.

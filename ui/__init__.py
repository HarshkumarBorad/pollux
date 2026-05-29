"""Pollux Streamlit UI.

A 4-page multi-agent system dashboard:

  💬 Chat       — employee Q&A with live progress streaming
  📦 Tickets    — customer support ticket triage + drafted replies
  📋 Workflows  — meeting transcripts → structured action items
  📜 Agent Log  — task history + per-task event timeline

Subscribes to the Phase 8 REST API (`POLLUX_API_URL`) and its WebSocket
`/tasks/{id}/stream` endpoint for live updates. No direct orchestrator
or DB access — the UI is a pure REST client.

Run:
    streamlit run ui/home.py
"""

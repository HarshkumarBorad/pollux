"""Pollux UI — home page.

Connectivity check, agent roster, recent task activity, and a nav-card grid
pointing at the four functional pages. Every section uses the unified card
chrome from `styles.py`, so heights and alignment stay consistent regardless
of agent description length.

Run:
    streamlit run ui/home.py
"""
from __future__ import annotations

import streamlit as st

from api_client import APIClient, APIError
from components import (
    render_agent_roster_card,
    render_nav_card,
    render_task_summary,
)
from styles import AGENT_STYLES, GLOBAL_CSS

st.set_page_config(
    page_title="Pollux",
    page_icon="🌟",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# --- Header -------------------------------------------------------------

st.title("🌟 Pollux")
st.markdown(
    "<div style='color:#475569;font-size:1.05rem;margin-top:-0.6rem;margin-bottom:1.5rem;'>"
    "<b>Multi-agent system for organizational task automation.</b> "
    "Six specialist agents working together — same business logic exposed via "
    "MCP, A2A, and this REST + UI surface."
    "</div>",
    unsafe_allow_html=True,
)

client = APIClient()

# --- System status ------------------------------------------------------

st.markdown("### System status")

status_cols = st.columns(4, gap="small")
try:
    health = client.health()
    with status_cols[0]:
        emoji = "🟢" if health["status"] == "ok" else "🟡"
        st.metric("API", f"{emoji} {health['status']}")
    with status_cols[1]:
        st.metric("Database", health.get("db", "unknown"))
    with status_cols[2]:
        st.metric("Agents", health.get("agents", 0))
    with status_cols[3]:
        try:
            tasks = client.list_tasks(limit=200)
            st.metric("Tasks", tasks.get("count", 0))
        except APIError:
            st.metric("Tasks", "—")
except APIError as exc:
    st.error(
        f"Cannot reach Pollux API at `{client.base_url}` — `{exc}`. "
        "Start it with `python -m api.server` and refresh."
    )
    st.stop()

# --- Agent roster -------------------------------------------------------

st.markdown("### Agent roster")
try:
    agents = client.list_agents()
    agent_list = agents.get("agents", [])
    if agent_list:
        # Always render in a 3-column grid for consistent card alignment
        # (6 agents → 2 rows of 3; if there are fewer, blanks are fine).
        rows = [agent_list[i : i + 3] for i in range(0, len(agent_list), 3)]
        for row in rows:
            cols = st.columns(3, gap="small")
            for col, agent in zip(cols, row):
                style = AGENT_STYLES.get(agent.get("id", ""), {
                    "icon": "❔",
                    "label": agent.get("id", "unknown"),
                    "color": "#64748b",
                    "bg": "#f1f5f9",
                })
                with col:
                    render_agent_roster_card(agent, style)
except APIError as exc:
    st.warning(f"Could not load agents: {exc}")

# --- Nav cards ----------------------------------------------------------

st.markdown("### Try Pollux")

nav_items = [
    ("💬", "Chat", "Ask HR or IT questions — Coordinator routes, Specialist answers, Escalation reviews.", "/Chat"),
    ("📦", "Tickets", "Submit customer support tickets — get a tone-shifted reply draft you can paste into your support tool.", "/Tickets"),
    ("📋", "Workflows", "Drop a meeting transcript — Ops Planner extracts action items with assignee, priority, and deadline.", "/Workflows"),
    ("📜", "Agent Log", "Browse the full task audit trail — per-task event timeline, status filters, error introspection.", "/Agent_Log"),
]
nav_cols = st.columns(4, gap="small")
for col, (emoji, title, description, page_url) in zip(nav_cols, nav_items):
    with col:
        render_nav_card(emoji, title, description, page_url=page_url)

st.caption("Click a card to jump in, or use the sidebar →")

# --- Recent activity -----------------------------------------------------

st.markdown("### Recent activity")
try:
    tasks_resp = client.list_tasks(limit=8)
    recent = tasks_resp.get("tasks", [])
    if not recent:
        st.info("No tasks yet. Try the **💬 Chat** page to submit one.")
    else:
        for task in recent:
            render_task_summary(task)
except APIError as exc:
    st.warning(f"Could not load recent tasks: {exc}")

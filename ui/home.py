"""Pollux UI — home page.

Lightweight landing page: shows API connectivity, agent roster, recent task
activity, and a nav-card grid pointing at the four functional pages.

Run:
    streamlit run ui/home.py
"""
from __future__ import annotations

import streamlit as st

from api_client import APIClient, APIError
from components import render_task_summary
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
    "**Multi-agent system for organizational task automation.** "
    "Six specialist agents working together — same business logic exposed "
    "via MCP, A2A, and this REST + UI surface."
)

client = APIClient()

# --- System status ------------------------------------------------------

st.markdown("### System status")

status_cols = st.columns(4)
try:
    health = client.health()
    with status_cols[0]:
        st.metric(
            "API",
            f"{'🟢' if health['status'] == 'ok' else '🟡'} {health['status']}",
        )
    with status_cols[1]:
        st.metric("Database", health.get("db", "unknown"))
    with status_cols[2]:
        st.metric("Agents", health.get("agents", 0))
    with status_cols[3]:
        try:
            tasks = client.list_tasks(limit=200)
            st.metric("Tasks (recent)", tasks.get("count", 0))
        except APIError:
            st.metric("Tasks (recent)", "—")
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
    agent_cols = st.columns(len(agents.get("agents", [])) or 1)
    for col, agent in zip(agent_cols, agents.get("agents", [])):
        agent_id = agent.get("id", "")
        style = AGENT_STYLES.get(agent_id, {"icon": "❔", "label": agent_id, "bg": "#f1f5f9", "color": "#64748b"})
        with col:
            st.markdown(
                f"<div style='background:{style['bg']};border-left:4px solid {style['color']};"
                "padding:14px;border-radius:8px;height:120px;'>"
                f"<div style='font-size:1.4rem;'>{style['icon']}</div>"
                f"<div style='font-weight:600;color:{style['color']};margin-top:4px;'>{style['label']}</div>"
                f"<div style='font-size:0.8rem;color:#475569;margin-top:6px;'>{agent.get('description', '')[:80]}…</div>"
                "</div>",
                unsafe_allow_html=True,
            )
except APIError as exc:
    st.warning(f"Could not load agents: {exc}")

# --- Nav cards ----------------------------------------------------------

st.markdown("### Try Pollux")

nav_cols = st.columns(4)
nav_items = [
    ("💬", "Chat", "Ask HR or IT questions — Coordinator routes, Specialist answers, Escalation reviews."),
    ("📦", "Tickets", "Submit customer support tickets — get a tone-shifted reply draft you can paste into your support tool."),
    ("📋", "Workflows", "Drop a meeting transcript — Ops Planner extracts action items with assignee, priority, and deadline."),
    ("📜", "Agent Log", "Browse the full task audit trail — per-task event timeline, status filters, error introspection."),
]
for col, (emoji, title, description) in zip(nav_cols, nav_items):
    with col:
        with st.container(border=True):
            st.markdown(f"### {emoji} {title}")
            st.caption(description)

st.caption("← use the sidebar to switch pages")

# --- Recent activity -----------------------------------------------------

st.markdown("### Recent activity")
try:
    tasks_resp = client.list_tasks(limit=8)
    recent = tasks_resp.get("tasks", [])
    if not recent:
        st.info("No tasks yet. Try the **Chat** page to submit one.")
    else:
        for task in recent:
            with st.container(border=True):
                render_task_summary(task)
except APIError as exc:
    st.warning(f"Could not load recent tasks: {exc}")

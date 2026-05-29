"""Reusable Streamlit components shared across the four pages.

Kept dependency-light — pure rendering, no API calls. Callers fetch the
data, components do the layout + per-agent / per-status styling.
"""
from __future__ import annotations

import json
from typing import Any

import streamlit as st

from styles import agent_pill, status_pill, task_type_pill


def render_task_summary(task: dict, show_id: bool = True) -> None:
    """One-line task summary — pills for type / status / agent, optional id."""
    cols = st.columns([2, 2, 2, 3])
    with cols[0]:
        st.markdown(task_type_pill(task.get("type", "")), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(status_pill(task.get("status", "")), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(agent_pill(task.get("assigned_agent")), unsafe_allow_html=True)
    with cols[3]:
        if show_id:
            st.code(task.get("id", ""), language=None)


def render_event(event: dict) -> None:
    """Render a single WSEvent envelope (the JSON shape the WebSocket emits)."""
    kind = event.get("type")
    data = event.get("data", {})

    if kind == "status":
        st.markdown(
            "**📍 Initial status:** "
            + status_pill(data.get("status", "unknown")),
            unsafe_allow_html=True,
        )
    elif kind == "event":
        ev_type = data.get("event_type", "event")
        payload = data.get("payload") or {}
        # Compact payload preview for the timeline.
        payload_preview = json.dumps(payload, default=str)
        if len(payload_preview) > 140:
            payload_preview = payload_preview[:140] + "…"
        st.markdown(
            f"<div class='pollux-event-row'><b>⚡ {ev_type}</b> "
            f"<span style='color:#64748b;'>{payload_preview}</span></div>",
            unsafe_allow_html=True,
        )
    elif kind == "result":
        render_task_result(data)
    elif kind == "error":
        st.error(f"❌ {data.get('detail', 'Unknown error from server')}")
    else:
        st.warning(f"Unknown event type: {kind!r}")


def render_task_result(task: dict) -> None:
    """Render a final task — answer + citations + QA verdict."""
    result = task.get("result") or {}
    summary = result.get("summary") or "_(no answer)_"
    confidence = result.get("confidence")
    verdict = (result.get("artifacts") or {}).get("qa_verdict")

    st.markdown("### 💡 Answer")
    with st.container(border=True):
        st.markdown(summary)

    citations = result.get("citations") or []
    if citations:
        st.markdown("### 📑 Sources")
        for i, c in enumerate(citations, 1):
            score = c.get("score")
            score_label = f" · confidence {score:.2f}" if score is not None else ""
            domain = c.get("domain") or ""
            domain_label = f" [{domain}]" if domain else ""
            st.markdown(
                f"<div class='pollux-citation'>"
                f"<b>[{i}]{domain_label}</b> {c.get('source', 'unknown')}{score_label}<br/>"
                f"<span style='color:#64748b;font-size:0.9rem;'>{c.get('text', '')[:280]}</span>"
                "</div>",
                unsafe_allow_html=True,
            )

    # Footer with metadata.
    footer = []
    if task.get("assigned_agent"):
        footer.append(f"**Assigned:** {task['assigned_agent']}")
    if verdict:
        footer.append(f"**QA:** {verdict}")
    if confidence is not None:
        footer.append(f"**Confidence:** {confidence:.2f}")
    if footer:
        st.caption(" · ".join(footer))


def render_event_timeline(events: list[dict]) -> None:
    """Render a chronological list of task_event rows (from GET /tasks/{id})."""
    if not events:
        st.info("No events yet.")
        return
    for ev in events:
        ts = ev.get("created_at", "")
        ev_type = ev.get("event_type", "?")
        payload = ev.get("payload") or {}
        payload_preview = json.dumps(payload, default=str)
        if len(payload_preview) > 200:
            payload_preview = payload_preview[:200] + "…"
        st.markdown(
            f"<div class='pollux-event-row'>"
            f"<span style='color:#94a3b8;'>{ts}</span> "
            f"<b>{ev_type}</b> "
            f"<span style='color:#64748b;'>{payload_preview}</span>"
            "</div>",
            unsafe_allow_html=True,
        )

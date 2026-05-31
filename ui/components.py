"""Reusable Streamlit components shared across the four pages.

Kept dependency-light — pure rendering, no API calls. Callers fetch the
data, components do the layout + per-agent / per-status / per-task-type
styling. All visual identity lives in `styles.py`.
"""
from __future__ import annotations

import html
import json
from typing import Any

import streamlit as st

from styles import agent_pill, status_pill, task_type_pill


def _short_id(task_id: str) -> str:
    """Display the first 8 chars of a UUID — full ID is hover-only / copy-only."""
    return (task_id or "")[:8]


def _esc(value: Any) -> str:
    return html.escape(str(value) if value is not None else "")


def render_task_summary(task: dict, *, show_id: bool = True) -> None:
    """One-line task summary as a unified card (pills left, meta right).

    Uses a single HTML card instead of Streamlit columns — keeps pills and
    metadata cleanly aligned across rows even when the task type, status,
    or agent labels have different widths.
    """
    type_html = task_type_pill(task.get("type", ""))
    status_html = status_pill(task.get("status", ""))
    agent_html = agent_pill(task.get("assigned_agent"))

    meta_bits = []
    if show_id and task.get("id"):
        meta_bits.append(f"<code>{_esc(_short_id(task['id']))}</code>")
    if task.get("updated_at"):
        meta_bits.append(f"<span>{_esc(task['updated_at'][:19].replace('T', ' '))}</span>")
    meta_html = " · ".join(meta_bits)

    st.markdown(
        f"""
        <div class='pollux-card'>
            <div class='pollux-card-row'>
                <div class='pollux-card-pills'>
                    {type_html}{status_html}{agent_html}
                </div>
                <div class='pollux-card-meta'>{meta_html}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_event(event: dict) -> None:
    """Render a single WSEvent envelope (the JSON the WebSocket emits).

    Each kind gets a colored left-border + fade/slide-in animation, so events
    accumulate visibly as the pipeline runs.
    """
    kind = event.get("type")
    data = event.get("data", {})

    if kind == "status":
        status = data.get("status", "unknown")
        st.markdown(
            f"<div class='pollux-event-row pollux-event-status'>"
            f"<b>📍 Initial status:</b> {status_pill(status)}"
            "</div>",
            unsafe_allow_html=True,
        )
    elif kind == "event":
        ev_type = data.get("event_type", "event")
        payload = data.get("payload") or {}
        payload_preview = json.dumps(payload, default=str)
        if len(payload_preview) > 140:
            payload_preview = payload_preview[:140] + "…"
        st.markdown(
            f"<div class='pollux-event-row'>"
            f"<b>⚡ {_esc(ev_type)}</b> "
            f"<span class='pollux-text-muted'>{_esc(payload_preview)}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    elif kind == "result":
        # The "result" envelope contains the full Task — hand off to the
        # dedicated answer renderer.
        render_task_result(data)
    elif kind == "error":
        detail = data.get("detail", "Unknown error from server")
        st.markdown(
            f"<div class='pollux-event-row pollux-event-error'>"
            f"<b>❌ Error</b> <span class='pollux-text-secondary'>{_esc(detail)}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"Unknown event type: {kind!r}")


def render_task_result(task: dict) -> None:
    """Render the final task — answer panel + citations + QA footer."""
    result = task.get("result") or {}
    summary = result.get("summary") or "_(no answer)_"
    confidence = result.get("confidence")
    verdict = (result.get("artifacts") or {}).get("qa_verdict")

    st.markdown("### 💡 Answer")
    # Use Streamlit's markdown renderer inside our custom-styled container.
    answer_container = st.container()
    with answer_container:
        st.markdown(
            "<div class='pollux-answer'>", unsafe_allow_html=True
        )
        st.markdown(summary)
        st.markdown("</div>", unsafe_allow_html=True)

    citations = result.get("citations") or []
    if citations:
        st.markdown("### 📑 Sources")
        for i, c in enumerate(citations, 1):
            score = c.get("score")
            score_html = (
                f" · <span class='pollux-text-muted'>confidence {score:.2f}</span>"
                if score is not None else ""
            )
            domain = c.get("domain") or ""
            domain_html = (
                f"<span class='pollux-pill' style='background:#f1f5f9;color:#475569;font-size:0.72rem;'>{_esc(domain)}</span> "
                if domain else ""
            )
            source = c.get("source", "unknown")
            text_preview = (c.get("text") or "")[:280]
            st.markdown(
                f"""
                <div class='pollux-citation'>
                    <div class='pollux-citation-meta'>
                        <span>[{i}]</span>{domain_html}<span>{_esc(source)}</span>{score_html}
                    </div>
                    <div class='pollux-citation-text'>{_esc(text_preview)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Footer: assigned agent + QA verdict + confidence — laid out as a pill row.
    footer_bits = []
    if task.get("assigned_agent"):
        footer_bits.append(f"<b>Assigned:</b> {_esc(task['assigned_agent'])}")
    if verdict:
        footer_bits.append(f"<b>QA:</b> {_esc(verdict)}")
    if confidence is not None:
        footer_bits.append(f"<b>Confidence:</b> {confidence:.2f}")
    if footer_bits:
        st.markdown(
            f"<div style='margin-top:14px;font-size:0.85rem;color:#475569;'>"
            f"{' &nbsp;·&nbsp; '.join(footer_bits)}"
            "</div>",
            unsafe_allow_html=True,
        )


def render_event_timeline(events: list[dict]) -> None:
    """Render a chronological list of task_event rows (from GET /tasks/{id})."""
    if not events:
        st.info("No events yet.")
        return
    for ev in events:
        ts = (ev.get("created_at") or "")[:19].replace("T", " ")
        ev_type = ev.get("event_type", "?")
        payload = ev.get("payload") or {}
        payload_preview = json.dumps(payload, default=str)
        if len(payload_preview) > 200:
            payload_preview = payload_preview[:200] + "…"
        st.markdown(
            f"<div class='pollux-event-row'>"
            f"<span class='pollux-text-muted'>{_esc(ts)}</span> "
            f"<b>{_esc(ev_type)}</b> "
            f"<span class='pollux-text-secondary'>{_esc(payload_preview)}</span>"
            "</div>",
            unsafe_allow_html=True,
        )


def render_nav_card(emoji: str, title: str, description: str) -> None:
    """Polished home-page nav card with consistent height + hover lift."""
    st.markdown(
        f"""
        <div class='pollux-nav-card'>
            <div style='font-size:1.6rem;'>{emoji}</div>
            <div class='pollux-nav-title'>{_esc(title)}</div>
            <div class='pollux-nav-desc'>{_esc(description)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_agent_roster_card(agent: dict, style: dict) -> None:
    """Polished home-page agent card with the agent's accent color on the left edge."""
    description = (agent.get("description") or "")
    if len(description) > 110:
        description = description[:110].rstrip() + "…"
    st.markdown(
        f"""
        <div class='pollux-agent-card' style='border-left-color:{style["color"]};background:{style["bg"]}33;'>
            <div class='pollux-agent-icon'>{style["icon"]}</div>
            <div class='pollux-agent-name' style='color:{style["color"]};'>{_esc(style["label"])}</div>
            <div class='pollux-agent-desc'>{_esc(description)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

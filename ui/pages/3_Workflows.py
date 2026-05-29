"""📋 Workflows — meeting transcripts → structured action items."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from api_client import APIClient, APIError, stream_task_blocking
from components import render_event, render_task_result
from styles import GLOBAL_CSS

st.set_page_config(page_title="Workflows — Pollux", page_icon="📋", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

st.title("📋 Ops Workflows")
st.caption(
    "Drop a meeting transcript. The Ops Planner summarizes it and extracts "
    "action items as structured JSON (task / assignee / priority / deadline)."
)

client = APIClient()

# --- Submit form ---------------------------------------------------------

st.markdown("### New workflow")

input_method = st.radio(
    "Input method",
    ["Paste transcript", "Upload .txt file"],
    horizontal=True,
)

transcript = ""
if input_method == "Paste transcript":
    transcript = st.text_area(
        "Transcript",
        height=180,
        placeholder=(
            "Lina: Let's ship the billing migration this sprint.\n"
            "Marc: I can take the rollback plan by Friday.\n"
            "Lina: Great, also we need to draft the customer comms by Monday."
        ),
    )
else:
    uploaded = st.file_uploader("Upload transcript (.txt)", type=["txt"])
    if uploaded is not None:
        transcript = uploaded.getvalue().decode("utf-8", errors="ignore")
        st.caption(f"Loaded {len(transcript)} characters from `{uploaded.name}`")

col_a, col_b = st.columns([2, 1])
with col_a:
    meeting_title = st.text_input(
        "Meeting title (optional)", placeholder="Platform weekly"
    )
with col_b:
    attendees_raw = st.text_input(
        "Attendees (comma-separated)", placeholder="Lina, Marc"
    )
attendees = [a.strip() for a in attendees_raw.split(",") if a.strip()]

submit_clicked = st.button(
    "📤 Extract action items",
    type="primary",
    disabled=not transcript.strip(),
    use_container_width=False,
)

# --- Submit + stream -----------------------------------------------------

if submit_clicked:
    try:
        submit = client.submit_meeting(
            transcript=transcript,
            meeting_title=meeting_title or "Untitled meeting",
            attendees=attendees,
            wait=False,
        )
    except APIError as exc:
        st.error(f"Submission failed: {exc}")
        st.stop()

    task_id = str(submit.get("task_id", ""))
    st.success(f"Submitted task `{task_id}` — streaming progress…")

    st.markdown("**Pipeline progress**")
    live = st.container(border=True)
    final_placeholder = st.empty()

    def on_event(event: dict) -> None:
        with live:
            render_event(event)

    try:
        events = stream_task_blocking(task_id, on_event=on_event)
    except APIError as exc:
        final_placeholder.error(f"Stream error: {exc}")
        st.stop()

    # --- Render result + structured action-items table -------------------
    result_event = next((e for e in events if e.get("type") == "result"), None)
    if result_event:
        task = result_event["data"]
        with final_placeholder.container():
            render_task_result(task)

        subtasks = (task.get("result") or {}).get("artifacts", {}).get("subtasks", [])
        if subtasks:
            st.markdown("### 🎯 Action items")
            try:
                import pandas as pd

                df = pd.DataFrame(subtasks)
                # Normalize column order if present.
                preferred = [c for c in ["task", "assignee", "priority", "deadline"] if c in df.columns]
                others = [c for c in df.columns if c not in preferred]
                st.dataframe(df[preferred + others], use_container_width=True)
            except Exception:
                # Fallback if pandas isn't installed or the shape is weird.
                for st_i, st_item in enumerate(subtasks, 1):
                    st.markdown(f"**{st_i}.** {st_item}")
        else:
            st.info("Ops Planner did not extract any action items.")

# --- Recent workflows ----------------------------------------------------

st.markdown("---")
st.markdown("### Recent workflows")
try:
    recent = client.list_tasks(status=None, limit=20)
    ops_tasks = [t for t in recent.get("tasks", []) if t.get("type") == "ops_workflow"]
    if not ops_tasks:
        st.info("No workflows yet.")
    for task in ops_tasks:
        from components import render_task_summary

        with st.container(border=True):
            render_task_summary(task)
except APIError as exc:
    st.warning(f"Could not load workflows: {exc}")

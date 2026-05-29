"""📜 Agent Log — full task audit trail with per-task event timeline."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from api_client import APIClient, APIError
from components import render_event_timeline, render_task_result, render_task_summary
from styles import GLOBAL_CSS, STATUS_STYLES

st.set_page_config(page_title="Agent Log — Pollux", page_icon="📜", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

st.title("📜 Agent Log")
st.caption(
    "Every task ever submitted through any of the three client surfaces "
    "(REST, MCP, A2A) lands in the same SQLite store. This is the operational "
    "view across all of them."
)

client = APIClient()

# --- Filters -------------------------------------------------------------

st.markdown("### Filters")

filter_cols = st.columns([1, 1, 1, 1])
with filter_cols[0]:
    status_filter = st.selectbox(
        "Status",
        options=["(all)", *STATUS_STYLES.keys()],
        index=0,
    )
with filter_cols[1]:
    task_type_filter = st.selectbox(
        "Task type",
        options=["(all)", "employee_question", "customer_support", "ops_workflow"],
        index=0,
    )
with filter_cols[2]:
    limit = st.number_input("Limit", min_value=5, max_value=200, value=50, step=5)
with filter_cols[3]:
    st.write("")  # vertical spacer
    refresh = st.button("🔄 Refresh", use_container_width=True)

# --- Fetch ---------------------------------------------------------------

try:
    resp = client.list_tasks(
        status=status_filter if status_filter != "(all)" else None,
        limit=int(limit),
    )
    tasks = resp.get("tasks", [])
    if task_type_filter != "(all)":
        tasks = [t for t in tasks if t.get("type") == task_type_filter]
except APIError as exc:
    st.error(f"Could not load tasks: {exc}")
    st.stop()

# --- Status summary ------------------------------------------------------

if tasks:
    status_counts: dict[str, int] = {}
    for t in tasks:
        status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
    metric_cols = st.columns(len(STATUS_STYLES))
    for col, (status_key, style) in zip(metric_cols, STATUS_STYLES.items()):
        with col:
            st.metric(
                f"{style['icon']} {status_key.replace('_', ' ').title()}",
                status_counts.get(status_key, 0),
            )

st.markdown("---")

# --- Table of tasks ------------------------------------------------------

st.markdown(f"### {len(tasks)} task(s)")

if not tasks:
    st.info("No tasks matching the filters.")

for task in tasks:
    with st.container(border=True):
        cols = st.columns([6, 1])
        with cols[0]:
            render_task_summary(task)
        with cols[1]:
            if st.button(
                "Inspect",
                key=f"inspect_{task['id']}",
                use_container_width=True,
            ):
                st.session_state["inspect_task_id"] = task["id"]

# --- Inspect view --------------------------------------------------------

inspect_id = st.session_state.get("inspect_task_id")
if inspect_id:
    st.markdown("---")
    st.markdown(f"### 🔬 Task detail — `{inspect_id}`")
    try:
        detail = client.get_task(inspect_id)
        task = detail.get("task", {})
        events = detail.get("events", [])

        col_l, col_r = st.columns([2, 3])
        with col_l:
            st.markdown("**Metadata**")
            with st.container(border=True):
                render_task_summary(task)
                created = task.get("created_at", "")
                updated = task.get("updated_at", "")
                error = task.get("error")
                st.caption(f"Created: {created}")
                st.caption(f"Updated: {updated}")
                if error:
                    st.error(f"Error: {error}")

        with col_r:
            st.markdown("**Result**")
            if task.get("result"):
                render_task_result(task)
            else:
                st.info("No result yet — task is still in progress.")

        st.markdown("**Event timeline**")
        with st.container(border=True):
            render_event_timeline(events)
    except APIError as exc:
        st.warning(f"Could not load task: {exc}")

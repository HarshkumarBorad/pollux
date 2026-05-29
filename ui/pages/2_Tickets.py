"""📦 Tickets — customer support ticket inbox + drafted replies."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from api_client import APIClient, APIError, stream_task_blocking
from components import render_event, render_task_result, render_task_summary
from styles import GLOBAL_CSS

st.set_page_config(page_title="Tickets — Pollux", page_icon="📦", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

st.title("📦 Customer Ticket Inbox")
st.caption(
    "Submit a support ticket. The Customer-Facing Specialist drafts a "
    "tone-shifted reply you can paste straight into your support tool."
)

client = APIClient()

# --- Two-column layout: list / detail -------------------------------------

left, right = st.columns([2, 3])

with left:
    st.markdown("### Recent tickets")
    try:
        tasks_resp = client.list_tasks(status=None, limit=20)
        tasks = [t for t in tasks_resp.get("tasks", []) if t.get("type") == "customer_support"]
        if not tasks:
            st.info("No customer tickets yet.")
        for task in tasks:
            with st.container(border=True):
                render_task_summary(task)
                if st.button(
                    "View details", key=f"view_{task['id']}", use_container_width=True
                ):
                    st.session_state["selected_ticket_id"] = task["id"]
    except APIError as exc:
        st.warning(f"Could not load tickets: {exc}")

with right:
    st.markdown("### Submit a new ticket")
    with st.form("new_ticket_form", clear_on_submit=False):
        subject = st.text_input("Subject", placeholder="API key not working")
        body = st.text_area(
            "Body",
            placeholder="I rotated my key yesterday and now get 401s on every call.",
            height=120,
        )
        customer_id = st.text_input(
            "Customer ID (optional)", placeholder="cust_42"
        )
        submitted = st.form_submit_button("📨 Submit ticket", type="primary")

    if submitted:
        if not subject.strip() or not body.strip():
            st.error("Subject and body are required.")
        else:
            try:
                submit = client.submit_ticket(
                    subject=subject,
                    body=body,
                    customer_id=customer_id or None,
                    wait=False,
                )
            except APIError as exc:
                st.error(f"Submission failed: {exc}")
                st.stop()

            task_id = str(submit.get("task_id", ""))
            st.success(f"Submitted task `{task_id}` — streaming progress…")

            # Live progress.
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

            result_event = next((e for e in events if e.get("type") == "result"), None)
            if result_event:
                with final_placeholder.container():
                    render_task_result(result_event["data"])
                # Auto-select the just-submitted ticket on the left.
                st.session_state["selected_ticket_id"] = task_id

    # --- Selected ticket detail ------------------------------------------
    selected_id = st.session_state.get("selected_ticket_id")
    if selected_id:
        st.markdown("---")
        st.markdown(f"### Ticket detail — `{selected_id}`")
        try:
            detail = client.get_task(selected_id)
            render_task_result(detail.get("task", {}))
            with st.expander("Event timeline"):
                from components import render_event_timeline

                render_event_timeline(detail.get("events", []))
        except APIError as exc:
            st.warning(f"Could not load ticket: {exc}")

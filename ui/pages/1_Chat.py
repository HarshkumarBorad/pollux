"""💬 Chat — employee Q&A with live progress streaming.

Streamlit runs each page as a fresh script — pages don't share import paths
with the home script automatically. Manually add the `ui/` directory so
sibling modules (`api_client`, `components`, `styles`) are importable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from api_client import APIClient, APIError, stream_task_blocking
from components import render_event, render_task_result
from styles import GLOBAL_CSS

st.set_page_config(page_title="Chat — Pollux", page_icon="💬", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

st.title("💬 Chat with Pollux")
st.caption(
    "Coordinator picks HR or IT specialist based on your question. "
    "Specialist answers with citations. Escalation/QA reviews the answer."
)

client = APIClient()

# Per-session conversation history.
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []  # list[dict]: {role, content, task_id?, result?}

# --- Replay history ------------------------------------------------------

for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("task_id"):
            st.caption(f"task: `{msg['task_id']}`")
        if msg.get("result"):
            with st.expander("Inspect task result"):
                render_task_result(msg["result"])

# --- New question --------------------------------------------------------

question = st.chat_input("What's your question? (Press Enter to send)")
if question:
    # Persist the user turn.
    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Process the assistant turn — submit async, stream live, finalize.
    with st.chat_message("assistant"):
        try:
            submit = client.submit_question(question, wait=False)
        except APIError as exc:
            st.error(f"Submission failed: {exc}")
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": f"❌ Submission failed: {exc}"}
            )
            st.stop()

        task_id = str(submit.get("task_id", ""))
        st.caption(f"task: `{task_id}`")

        # Live event log placeholder + final answer placeholder.
        st.markdown("**Pipeline progress**")
        live = st.container(border=True)
        final = st.empty()

        rendered = {"count": 0}

        def on_event(event: dict) -> None:
            with live:
                render_event(event)
            rendered["count"] += 1

        try:
            events = stream_task_blocking(task_id, on_event=on_event)
        except APIError as exc:
            final.error(f"Stream error: {exc}")
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": f"❌ Stream error: {exc}", "task_id": task_id}
            )
            st.stop()

        # Final result envelope contains the full Task — render the answer.
        result_event = next((e for e in events if e.get("type") == "result"), None)
        if result_event:
            task = result_event["data"]
            with final.container():
                render_task_result(task)
            result_msg = (task.get("result") or {}).get("summary") or "_(no answer)_"
            st.session_state.chat_messages.append(
                {
                    "role": "assistant",
                    "content": result_msg,
                    "task_id": task_id,
                    "result": task,
                }
            )
        else:
            error_event = next((e for e in events if e.get("type") == "error"), None)
            detail = (error_event or {}).get("data", {}).get("detail", "Stream ended without a result")
            final.warning(detail)
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": f"⚠️ {detail}", "task_id": task_id}
            )

# --- Sidebar -------------------------------------------------------------

with st.sidebar:
    st.markdown("### Tips")
    st.caption(
        "Coordinator's classification uses **OpenAI** when `OPENAI_API_KEY` is "
        "set, otherwise HF. Specialists always use HF Inference."
    )
    st.markdown("### Suggestions")
    suggestions = [
        "What is the leave policy?",
        "How do I authenticate API requests?",
        "How many sick days do I get?",
        "Which Python version is required for the SDK?",
    ]
    for sugg in suggestions:
        if st.button(sugg, use_container_width=True):
            # Streamlit chat_input is the source of truth for now — print as hint.
            st.toast("Copy the suggestion into the chat input below.", icon="💡")

    st.markdown("---")
    if st.button("🧹 Clear conversation", use_container_width=True):
        st.session_state.chat_messages = []
        st.rerun()

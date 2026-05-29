"""Visual identity for the Pollux UI.

One registry of per-agent / per-status / per-task-type styling so every page
keeps the same color story — important for the "this is one product" feel.
"""
from __future__ import annotations

# Per-agent identity. Keys match the agent.id values in the registry.
AGENT_STYLES: dict[str, dict[str, str]] = {
    "coordinator": {"icon": "🧭", "label": "Coordinator", "color": "#6366f1", "bg": "#eef2ff"},
    "hr_specialist": {"icon": "🧑‍💼", "label": "HR Specialist", "color": "#1d4ed8", "bg": "#dbeafe"},
    "it_specialist": {"icon": "🔧", "label": "IT Specialist", "color": "#047857", "bg": "#d1fae5"},
    "customer_facing": {"icon": "📦", "label": "Customer-Facing", "color": "#b45309", "bg": "#fef3c7"},
    "ops_planner": {"icon": "📋", "label": "Ops Planner", "color": "#7c3aed", "bg": "#ede9fe"},
    "escalation": {"icon": "🚨", "label": "Escalation/QA", "color": "#b91c1c", "bg": "#fee2e2"},
}

# Per-status identity. Keys match TaskStatus.value strings.
STATUS_STYLES: dict[str, dict[str, str]] = {
    "pending": {"icon": "⏳", "color": "#475569", "bg": "#f1f5f9"},
    "planned": {"icon": "📍", "color": "#0369a1", "bg": "#e0f2fe"},
    "in_progress": {"icon": "⚙️", "color": "#b45309", "bg": "#fef3c7"},
    "completed": {"icon": "✅", "color": "#047857", "bg": "#d1fae5"},
    "failed": {"icon": "❌", "color": "#b91c1c", "bg": "#fee2e2"},
    "escalated": {"icon": "🚨", "color": "#dc2626", "bg": "#fef2f2"},
}

# Per-task-type identity. Keys match TaskType.value strings.
TASK_TYPE_STYLES: dict[str, dict[str, str]] = {
    "employee_question": {"icon": "❓", "label": "Employee Q&A", "color": "#1d4ed8"},
    "customer_support": {"icon": "📦", "label": "Customer Ticket", "color": "#b45309"},
    "ops_workflow": {"icon": "📋", "label": "Ops Workflow", "color": "#7c3aed"},
}


def _pill_html(text: str, fg: str, bg: str) -> str:
    return (
        f"<span style='background:{bg};color:{fg};padding:3px 10px;"
        "border-radius:999px;font-size:0.82rem;font-weight:600;white-space:nowrap;'>"
        f"{text}</span>"
    )


def agent_pill(agent_id: str | None) -> str:
    if not agent_id:
        return _pill_html("— unassigned —", "#64748b", "#f1f5f9")
    s = AGENT_STYLES.get(agent_id, {"icon": "❔", "label": agent_id, "color": "#64748b", "bg": "#f1f5f9"})
    return _pill_html(f"{s['icon']} {s['label']}", s["color"], s["bg"])


def status_pill(status: str) -> str:
    s = STATUS_STYLES.get(status, {"icon": "❔", "color": "#64748b", "bg": "#f1f5f9"})
    return _pill_html(f"{s['icon']} {status.replace('_', ' ').title()}", s["color"], s["bg"])


def task_type_pill(task_type: str) -> str:
    s = TASK_TYPE_STYLES.get(
        task_type, {"icon": "❔", "label": task_type, "color": "#64748b"}
    )
    return _pill_html(f"{s['icon']} {s['label']}", s["color"], "#f1f5f9")


# Global CSS — injected once per page via `st.markdown(GLOBAL_CSS, unsafe_allow_html=True)`.
GLOBAL_CSS = """
<style>
    .block-container { padding-top: 2rem; }
    h1 {
        background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 800;
    }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px;
    }
    .pollux-event-row {
        padding: 6px 10px;
        border-left: 3px solid #cbd5e1;
        background: #f8fafc;
        margin-bottom: 4px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 0.85rem;
    }
    .pollux-citation {
        padding: 10px 12px;
        background: #f8fafc;
        border-left: 4px solid #6366f1;
        border-radius: 6px;
        margin-bottom: 8px;
    }
</style>
"""

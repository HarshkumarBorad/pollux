"""Visual identity for the Pollux UI.

One registry of per-agent / per-status / per-task-type styling so every page
keeps the same color story. The CSS bundle at the bottom of this file is
injected once per page via `st.markdown(GLOBAL_CSS, unsafe_allow_html=True)`
and powers:
  - `pollux-card`  — unified card chrome with hover lift + fade-in animation
  - `pollux-pill`  — badge style used by `agent_pill`, `status_pill`, etc.
  - `pollux-fade-in-*` keyframes — subtle reveal animations for events,
    answers, and other dynamically rendered blocks
  - per-widget polish on `stMetric`, `stContainer`, `stTabs`, headings
"""
from __future__ import annotations

# Per-agent identity. Keys match the agent.id values in the registry.
AGENT_STYLES: dict[str, dict[str, str]] = {
    "coordinator":     {"icon": "🧭", "label": "Coordinator",     "color": "#4f46e5", "bg": "#eef2ff"},
    "hr_specialist":   {"icon": "🧑‍💼", "label": "HR Specialist",   "color": "#1d4ed8", "bg": "#dbeafe"},
    "it_specialist":   {"icon": "🔧", "label": "IT Specialist",   "color": "#047857", "bg": "#d1fae5"},
    "customer_facing": {"icon": "📦", "label": "Customer-Facing", "color": "#b45309", "bg": "#fef3c7"},
    "ops_planner":     {"icon": "📋", "label": "Ops Planner",     "color": "#7c3aed", "bg": "#ede9fe"},
    "escalation":      {"icon": "🚨", "label": "Escalation/QA",   "color": "#b91c1c", "bg": "#fee2e2"},
}

# Per-status identity. Keys match TaskStatus.value strings.
STATUS_STYLES: dict[str, dict[str, str]] = {
    "pending":     {"icon": "⏳", "color": "#475569", "bg": "#f1f5f9"},
    "planned":     {"icon": "📍", "color": "#0369a1", "bg": "#e0f2fe"},
    "in_progress": {"icon": "⚙️", "color": "#b45309", "bg": "#fef3c7"},
    "completed":   {"icon": "✅", "color": "#047857", "bg": "#d1fae5"},
    "failed":      {"icon": "❌", "color": "#b91c1c", "bg": "#fee2e2"},
    "escalated":   {"icon": "🚨", "color": "#dc2626", "bg": "#fef2f2"},
}

# Per-task-type identity. Keys match TaskType.value strings.
TASK_TYPE_STYLES: dict[str, dict[str, str]] = {
    "employee_question": {"icon": "❓", "label": "Employee Q&A",     "color": "#1d4ed8", "bg": "#dbeafe"},
    "customer_support":  {"icon": "📦", "label": "Customer Ticket",  "color": "#b45309", "bg": "#fef3c7"},
    "ops_workflow":      {"icon": "📋", "label": "Ops Workflow",     "color": "#7c3aed", "bg": "#ede9fe"},
}

_FALLBACK_STYLE = {"icon": "❔", "label": "—", "color": "#64748b", "bg": "#f1f5f9"}


def _pill_html(text: str, fg: str, bg: str) -> str:
    """Inline pill badge. Uses class `pollux-pill` for hover transitions."""
    return (
        f"<span class='pollux-pill' style='background:{bg};color:{fg};'>"
        f"{text}</span>"
    )


def agent_pill(agent_id: str | None) -> str:
    if not agent_id:
        return _pill_html("— unassigned —", "#64748b", "#f1f5f9")
    s = AGENT_STYLES.get(agent_id, dict(_FALLBACK_STYLE, label=agent_id))
    return _pill_html(f"{s['icon']} {s['label']}", s["color"], s["bg"])


def status_pill(status: str) -> str:
    s = STATUS_STYLES.get(status, _FALLBACK_STYLE)
    return _pill_html(
        f"{s['icon']} {status.replace('_', ' ').title()}", s["color"], s["bg"]
    )


def task_type_pill(task_type: str) -> str:
    s = TASK_TYPE_STYLES.get(task_type, dict(_FALLBACK_STYLE, label=task_type))
    return _pill_html(f"{s['icon']} {s['label']}", s["color"], s["bg"])


# --- Global CSS bundle ----------------------------------------------------

GLOBAL_CSS = """
<style>
/* ===== Page chrome ===================================================== */
.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1200px;
}

h1 {
    background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: 800 !important;
    letter-spacing: -0.02em;
}
h2, h3 {
    font-weight: 700 !important;
    letter-spacing: -0.01em;
    color: #0f172a;
}

/* ===== Sidebar polish ================================================== */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    border-right: 1px solid #e2e8f0;
}

/* ===== Pills (badges) ================================================== */
.pollux-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
    white-space: nowrap;
    line-height: 1.4;
    transition: transform 160ms ease, box-shadow 160ms ease;
}
.pollux-pill:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.10);
}

/* ===== Cards (unified) ================================================= */
.pollux-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    transition: box-shadow 200ms ease, transform 200ms ease, border-color 200ms ease;
    animation: pollux-fade-in 320ms ease-out both;
}
.pollux-card:hover {
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
    transform: translateY(-1px);
    border-color: #cbd5e1;
}

.pollux-card-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
}
.pollux-card-pills {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}
.pollux-card-meta {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 0.82rem;
    color: #64748b;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
.pollux-card-meta code {
    background: #f1f5f9;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 0.78rem;
    color: #475569;
}

/* Tight stacking for lists of cards. */
.pollux-card + .pollux-card { margin-top: 0; }

/* ===== Agent roster cards (Home page) ================================== */
.pollux-agent-card {
    background: #ffffff;
    border-radius: 12px;
    padding: 16px 18px;
    border: 1px solid #e2e8f0;
    border-left-width: 4px;
    min-height: 140px;
    display: flex;
    flex-direction: column;
    transition: transform 200ms ease, box-shadow 200ms ease;
    animation: pollux-fade-in 360ms ease-out both;
}
.pollux-agent-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
}
.pollux-agent-card .pollux-agent-icon {
    font-size: 1.6rem;
    line-height: 1;
}
.pollux-agent-card .pollux-agent-name {
    margin-top: 8px;
    font-weight: 700;
    font-size: 1rem;
    letter-spacing: -0.01em;
}
.pollux-agent-card .pollux-agent-desc {
    margin-top: 6px;
    color: #475569;
    font-size: 0.85rem;
    line-height: 1.4;
    flex-grow: 1;
}

/* ===== Nav cards ======================================================= */
.pollux-nav-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px;
    min-height: 130px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    transition: transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease;
    animation: pollux-fade-in 400ms ease-out both;
}
.pollux-nav-card:hover {
    border-color: #6366f1;
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(99, 102, 241, 0.10);
}
.pollux-nav-card .pollux-nav-title {
    font-weight: 700;
    font-size: 1.05rem;
    letter-spacing: -0.01em;
}
.pollux-nav-card .pollux-nav-desc {
    color: #475569;
    font-size: 0.85rem;
    line-height: 1.45;
}

/* ===== Streamlit native widget polish ================================== */
div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    transition: box-shadow 200ms ease, transform 200ms ease;
}
div[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
}

div[data-testid="stExpander"] {
    border-radius: 10px !important;
    border-color: #e2e8f0 !important;
    transition: border-color 200ms ease;
}

button[data-baseweb="tab"] {
    font-weight: 600;
    font-size: 0.95rem;
}

/* ===== Event row (pipeline timeline) =================================== */
.pollux-event-row {
    padding: 8px 12px;
    border-left: 3px solid #cbd5e1;
    background: #f8fafc;
    margin-bottom: 6px;
    border-radius: 4px;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 0.86rem;
    line-height: 1.45;
    animation: pollux-slide-in-left 260ms ease-out both;
    transition: background 160ms ease, border-left-color 160ms ease;
}
.pollux-event-row:hover {
    background: #f1f5f9;
    border-left-color: #6366f1;
}
.pollux-event-row b { color: #1e293b; }
.pollux-event-row .pollux-text-muted { color: #94a3b8; }

/* Event-row variants per kind, picked up via inline class. */
.pollux-event-status { border-left-color: #6366f1; background: #eef2ff; }
.pollux-event-result { border-left-color: #10b981; background: #d1fae5; }
.pollux-event-error  { border-left-color: #ef4444; background: #fee2e2; }

/* ===== Citation cards ================================================== */
.pollux-citation {
    padding: 12px 14px;
    background: #f8fafc;
    border-left: 4px solid #6366f1;
    border-radius: 8px;
    margin-bottom: 10px;
    transition: transform 180ms ease, box-shadow 180ms ease;
    animation: pollux-fade-in 320ms ease-out both;
}
.pollux-citation:hover {
    transform: translateX(2px);
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.10);
}
.pollux-citation .pollux-citation-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
    color: #1e293b;
    margin-bottom: 4px;
}
.pollux-citation .pollux-citation-text {
    color: #475569;
    font-size: 0.88rem;
    line-height: 1.5;
}

/* ===== Answer panel ==================================================== */
.pollux-answer {
    padding: 18px 20px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
    animation: pollux-fade-in 360ms ease-out both;
    line-height: 1.6;
}
.pollux-answer h3 { margin-top: 0; }

/* ===== Utility classes ================================================= */
.pollux-text-muted   { color: #94a3b8; }
.pollux-text-secondary { color: #475569; }
.pollux-mono          { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 0.85rem; }
.pollux-divider       { height: 1px; background: #e2e8f0; margin: 18px 0; }

/* ===== Animations ====================================================== */
@keyframes pollux-fade-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes pollux-slide-in-left {
    from { opacity: 0; transform: translateX(-8px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes pollux-pulse {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.6; }
}

/* Apply pulse to any element marked .pollux-pulsing — used for "in progress"
   status badges while the pipeline is running. */
.pollux-pulsing { animation: pollux-pulse 1.4s ease-in-out infinite; }
</style>
"""

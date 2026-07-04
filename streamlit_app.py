from __future__ import annotations

import json
import queue
from pathlib import Path
import sys
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from autonomous_research_agent.graph import run_agent
from autonomous_research_agent.observability import RunLogger, make_json_safe


st.set_page_config(
    page_title="Autonomous Research Agent",
    page_icon="A",
    layout="wide",
    initial_sidebar_state="collapsed",
)


APP_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@500;600&display=swap');

    :root {
        --page: #f4f7f8;
        --surface: #ffffff;
        --surface-soft: #eef4f4;
        --ink: #111827;
        --muted: #5f6b78;
        --faint: #8a96a3;
        --line: #dbe3e6;
        --accent: #006d77;
        --accent-2: #3454d1;
        --accent-soft: #dff3f1;
        --warn-soft: #fff4dc;
        --warn-text: #7c4d00;
        --shadow: 0 10px 24px rgba(21, 36, 46, 0.08);
    }

    html, body, [class*="css"] {
        font-family: "IBM Plex Sans", sans-serif;
        letter-spacing: 0;
    }

    .stApp {
        color: var(--ink);
        background:
            linear-gradient(90deg, rgba(0,109,119,0.05) 1px, transparent 1px),
            linear-gradient(180deg, rgba(52,84,209,0.04) 1px, transparent 1px),
            var(--page);
        background-size: 32px 32px;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stSidebar"] {
        background: #f8fafb;
        border-left: 1px solid var(--line);
    }

    .block-container {
        max-width: 1180px;
        padding-top: 1.25rem;
        padding-bottom: 2.5rem;
    }

    .app-topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        padding: 0.3rem 0 1rem;
        border-bottom: 1px solid var(--line);
        margin-bottom: 1rem;
    }

    .brand {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        min-width: 0;
    }

    .brand-mark {
        width: 18px;
        height: 18px;
        border-radius: 4px;
        background: linear-gradient(135deg, var(--accent), var(--accent-2));
    }

    .brand-name {
        font-weight: 700;
        color: var(--ink);
        font-size: 1rem;
    }

    .topbar-meta {
        color: var(--muted);
        font-size: 0.88rem;
        text-align: right;
    }

    .query-shell {
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.92);
        border-radius: 8px;
        box-shadow: var(--shadow);
        padding: 1rem;
        margin-bottom: 1rem;
    }

    .query-title {
        font-family: "IBM Plex Serif", serif;
        font-size: 1.75rem;
        line-height: 1.2;
        margin: 0 0 0.35rem;
        color: var(--ink);
    }

    .query-subtitle {
        color: var(--muted);
        font-size: 0.95rem;
        margin-bottom: 0.9rem;
    }

    div[data-testid="stForm"] {
        border: 0;
        background: transparent;
        padding: 0;
    }

    div[data-testid="stTextInput"] input {
        min-height: 52px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: #ffffff;
        color: var(--ink);
        caret-color: var(--accent);
        cursor: text;
        font-size: 1rem;
        padding-left: 0.95rem;
    }

    div[data-testid="stTextInput"] input:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 2px rgba(0,109,119,0.12);
        outline: none;
    }

    div[data-testid="stFormSubmitButton"] button {
        min-height: 52px;
        border-radius: 8px;
        background: var(--accent);
        border: 1px solid var(--accent);
        color: white;
        font-weight: 700;
    }

    div[data-testid="stButton"] > button {
        border-radius: 8px;
        border: 1px solid var(--line);
        background: var(--surface);
        color: var(--ink);
        min-height: 38px;
        font-size: 0.88rem;
        box-shadow: none;
    }

    div[data-testid="stButton"] > button:hover {
        border-color: var(--accent);
        color: var(--accent);
    }

    .label-row {
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--faint);
        font-weight: 700;
        margin: 0.6rem 0 0.45rem;
    }

    .panel {
        border: 1px solid var(--line);
        border-radius: 8px;
        background: rgba(255,255,255,0.94);
        box-shadow: var(--shadow);
        padding: 1rem;
        margin-bottom: 1rem;
    }

    .panel-title {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.8rem;
        font-weight: 700;
        margin-bottom: 0.65rem;
    }

    .panel-kicker {
        color: var(--faint);
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 700;
    }

    .status-pill {
        display: inline-flex;
        align-items: center;
        padding: 0.22rem 0.55rem;
        border-radius: 999px;
        background: var(--accent-soft);
        color: var(--accent);
        font-size: 0.78rem;
        font-weight: 700;
        white-space: nowrap;
    }

    .timeline {
        display: grid;
        gap: 0.45rem;
    }

    .timeline-item {
        border: 1px solid #e5ecef;
        border-radius: 8px;
        background: #fbfcfd;
        padding: 0.55rem 0.65rem;
        color: #2f3a45;
        font-size: 0.88rem;
        line-height: 1.45;
    }

    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.65rem;
        margin-bottom: 1rem;
    }

    .metric {
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--surface);
        padding: 0.75rem;
    }

    .metric-value {
        font-size: 1.15rem;
        font-weight: 800;
        color: var(--ink);
    }

    .metric-label {
        color: var(--muted);
        font-size: 0.76rem;
        margin-top: 0.15rem;
    }

    .brief h2 {
        color: var(--accent);
        font-size: 0.95rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-top: 1rem;
    }

    .brief li {
        margin-bottom: 0.35rem;
        line-height: 1.55;
    }

    .empty-state {
        border: 1px dashed #b9c8ce;
        background: #f8fbfc;
        border-radius: 8px;
        padding: 1.1rem;
        color: var(--muted);
    }

    @keyframes pulse-dot {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%       { opacity: 0.35; transform: scale(0.82); }
    }

    .running-banner {
        border: 1.5px solid var(--accent);
        border-radius: 10px;
        background: linear-gradient(135deg, var(--accent-soft), rgba(255,255,255,0.9));
        padding: 1.15rem 1.3rem;
        display: flex;
        align-items: center;
        gap: 1rem;
        box-shadow: 0 4px 18px rgba(0,109,119,0.12);
    }

    .running-dot {
        flex-shrink: 0;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--accent);
        animation: pulse-dot 1.1s ease-in-out infinite;
    }

    .running-title {
        font-weight: 700;
        color: var(--accent);
        font-size: 0.95rem;
    }

    .running-sub {
        color: var(--muted);
        font-size: 0.82rem;
        margin-top: 0.2rem;
    }

    @media (max-width: 900px) {
        .app-topbar {
            align-items: flex-start;
            flex-direction: column;
        }

        .topbar-meta {
            text-align: left;
        }

        .metric-grid,
        .node-grid {
            grid-template-columns: 1fr;
        }
    }
</style>
"""


SUGGESTIONS = [
    "Latest developments in battery recycling policy in Europe",
    "Compare LangGraph and OpenAI Agents SDK for a junior AI engineer",
    "Recent AI chip supply chain risks for startups in 2026",
]




def init_state() -> None:
    st.session_state.setdefault("query_text", "")
    st.session_state.setdefault("recent_queries", [])
    st.session_state.setdefault("run_messages", [])
    st.session_state.setdefault("run_events", [])
    st.session_state.setdefault("run_result", None)
    st.session_state.setdefault("run_log_path", None)


def set_query(query: str) -> None:
    st.session_state.query_text = query


def push_recent_query(query: str) -> None:
    cleaned = query.strip()
    if not cleaned:
        return
    existing = [item for item in st.session_state.recent_queries if item != cleaned]
    st.session_state.recent_queries = [cleaned, *existing][:6]


def load_jsonl(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def summarize_status() -> str:
    if not st.session_state.run_messages:
        return "Ready"
    latest = st.session_state.run_messages[-1].replace("[agent] ", "")
    if "Run completed" in latest:
        return "Complete"
    if "Starting node" in latest:
        return latest.replace("Starting node: ", "Running ")
    return latest


def get_references(result: dict[str, Any] | None) -> list[Any]:
    if not result or not result.get("summary"):
        return []
    summary = result["summary"]
    return summary.references if hasattr(summary, "references") else summary.get("references", [])




def render_header() -> None:
    st.markdown(
        """
        <div class="app-topbar">
            <div class="brand">
                <div class="brand-mark"></div>
                <div>
                    <div class="brand-name">Autonomous Research Agent</div>
                    <div class="topbar-meta">OpenAI + LangGraph research workflow</div>
                </div>
            </div>
            <div class="topbar-meta">Traced with LangSmith. Local JSONL logs saved per run.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_query_panel() -> tuple[bool, str]:
    st.markdown(
        """
        <div class="query-shell">
            <div class="query-title">Research console</div>
            <div class="query-subtitle">Enter a topic and the agent will search, validate, deduplicate, and synthesize a sourced brief.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("research_form", clear_on_submit=False):
        query = st.text_input(
            "Research query",
            key="query_text",
            placeholder="Example: latest developments in battery recycling policy in Europe",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Run Research", use_container_width=True, type="primary")

    st.markdown('<div class="label-row">Suggested queries</div>', unsafe_allow_html=True)
    suggestion_cols = st.columns(len(SUGGESTIONS))
    for index, suggestion in enumerate(SUGGESTIONS):
        suggestion_cols[index].button(
            suggestion,
            use_container_width=True,
            key=f"suggestion-{index}",
            on_click=set_query,
            args=(suggestion,),
        )

    if st.session_state.recent_queries:
        st.markdown('<div class="label-row">Recent searches</div>', unsafe_allow_html=True)
        recent_cols = st.columns(min(3, len(st.session_state.recent_queries)))
        for index, recent in enumerate(st.session_state.recent_queries[:3]):
            recent_cols[index].button(
                recent,
                use_container_width=True,
                key=f"recent-{index}-{recent}",
                on_click=set_query,
                args=(recent,),
            )

    return submitted, query


def render_progress() -> None:
    status = summarize_status()
    messages = st.session_state.run_messages[-8:]
    timeline = "".join(f'<div class="timeline-item">{message}</div>' for message in messages)
    if not timeline:
        timeline = '<div class="timeline-item">Submit a query to start the graph.</div>'

    st.markdown(
        f"""
        <div class="panel">
            <div class="panel-title">
                <span>Run status</span>
                <span class="status-pill">{status}</span>
            </div>
            <div class="timeline">{timeline}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def render_running_banner() -> None:
    st.markdown(
        """
        <div class="running-banner">
            <div class="running-dot"></div>
            <div>
                <div class="running-title">Research in progress…</div>
                <div class="running-sub">Searching, validating, and synthesising sources. This usually takes 30–90 seconds.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(result: dict[str, Any] | None) -> None:
    attempts = result.get("attempt_count", 0) if result else 0
    references = len(get_references(result))
    events = len(st.session_state.run_events)
    confidence = "Best effort" if result and result.get("low_confidence") else "Normal"
    st.markdown(
        f"""
        <div class="metric-grid">
            <div class="metric"><div class="metric-value">{attempts}</div><div class="metric-label">Attempts</div></div>
            <div class="metric"><div class="metric-value">{references}</div><div class="metric-label">References</div></div>
            <div class="metric"><div class="metric-value">{events}</div><div class="metric-label">Events</div></div>
            <div class="metric"><div class="metric-value">{confidence}</div><div class="metric-label">Mode</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_results(result: dict[str, Any] | None) -> None:
    render_metrics(result)
    if not result:
        st.markdown(
            """
            <div class="empty-state">
                No research brief yet. Run a query and the answer, sources, reasoning, and logs will appear here.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div class="panel"><div class="panel-title">Research brief</div><div class="brief">', unsafe_allow_html=True)
    st.markdown(result.get("final_response") or "No response generated.")
    st.markdown("</div></div>", unsafe_allow_html=True)

    references = get_references(result)
    detail_tabs = st.tabs(["Sources", "Reasoning", "JSONL events"])
    with detail_tabs[0]:
        if not references:
            st.caption("No references found.")
        for reference in references:
            ref_id = getattr(reference, "id", None) or reference.get("id")
            title = getattr(reference, "title", None) or reference.get("title")
            url = getattr(reference, "url", None) or reference.get("url")
            source_tool = getattr(reference, "source_tool", None) or reference.get("source_tool")
            if url:
                st.markdown(f"- `{ref_id}` [{title}]({url}) via `{source_tool}`")
            else:
                st.markdown(f"- `{ref_id}` {title} via `{source_tool}`")
    with detail_tabs[1]:
        if result.get("reasoning_log"):
            for line in result["reasoning_log"]:
                st.code(line, language="text")
        else:
            st.caption("No reasoning entries found.")
    with detail_tabs[2]:
        entries = load_jsonl(result.get("run_log_path"))
        if entries:
            st.json(entries[-12:])
        else:
            st.caption("No JSONL events found.")




def render_sidebar() -> None:
    st.sidebar.markdown("## Operator view")
    st.sidebar.caption("Local run metadata and recent activity.")
    if st.session_state.run_log_path:
        st.sidebar.write(f"Log: `{st.session_state.run_log_path}`")
    entries = load_jsonl(st.session_state.run_log_path)
    with st.sidebar.expander("Recent events", expanded=False):
        if entries:
            st.json(entries[-8:])
        else:
            st.caption("No events yet.")


def run_query(query: str) -> None:
    st.session_state.run_messages = []
    st.session_state.run_events = []
    st.session_state.run_result = None
    st.session_state.run_log_path = None

    # Thread-safe queues: background threads (LangGraph’s ThreadPoolExecutor for
    # parallel research_worker nodes) cannot access st.session_state directly.
    # Callbacks push into these queues; we drain them on the main thread after
    # run_agent() returns.
    _msg_queue: queue.Queue[str] = queue.Queue()
    _evt_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()

    def handle_message(message: str) -> None:
        _msg_queue.put(message)

    def handle_event(event: str, payload: dict[str, Any]) -> None:
        _evt_queue.put((event, payload))

    logger = RunLogger(
        echo_terminal=False,
        message_callback=handle_message,
        event_callback=handle_event,
    )
    st.session_state.run_log_path = str(logger.log_path)
    result = run_agent(query, logger=logger)

    # Back on the main Streamlit thread — drain queues into session_state.
    while not _msg_queue.empty():
        st.session_state.run_messages.append(_msg_queue.get_nowait())
    while not _evt_queue.empty():
        event, payload = _evt_queue.get_nowait()
        st.session_state.run_events.append({"event": event, "payload": payload})
        st.session_state.run_log_path = payload.get("payload", {}).get(
            "log_path", st.session_state.run_log_path
        )

    st.session_state.run_result = result
    st.session_state.run_log_path = result.get("run_log_path")
    push_recent_query(query)


def main() -> None:
    init_state()
    st.markdown(APP_CSS, unsafe_allow_html=True)
    render_header()

    submitted, query = render_query_panel()

    left_col, right_col = st.columns([1.55, 0.9], gap="large")
    with right_col:
        status_slot = st.empty()
    with left_col:
        result_slot = st.empty()

    with status_slot.container():
        render_progress()
    with result_slot.container():
        render_results(st.session_state.run_result)

    if submitted and query.strip():
        # Render the running banner immediately into the slot before the
        # blocking run_agent call — st.empty() flushes to the browser right away.
        with status_slot.container():
            render_running_banner()
        run_query(query.strip())
        # Replace the banner with the completed run-status log.
        with status_slot.container():
            render_progress()
        with result_slot.container():
            render_results(st.session_state.run_result)

    render_sidebar()


if __name__ == "__main__":
    main()

"""Session manager: multiple independent analysis sessions in memory."""

from __future__ import annotations

import re
from datetime import datetime
import streamlit as st


SESSION_KEYS = [
    "regulatory_files", "control_files", "process_files",
    "regulatory_chunks", "control_chunks", "process_chunks",
    "phase_1_draft", "phase_1_approved",
    "phase_2_draft", "phase_2_approved",
    "phase_3_draft", "phase_3_approved",
    "phase_1_complete", "phase_2_complete", "phase_3_complete",
    # phase_*_history: in-memory feedback only. Exports and meta.json use approved rows only.
    "phase_1_history", "phase_2_history", "phase_3_history",
    "verdict",
    "current_page",
    "regulatory_fp", "control_fp", "process_fp",
]

DEFAULTS = {
    "regulatory_files": [],
    "control_files": [],
    "process_files": [],
    "regulatory_chunks": [],
    "control_chunks": [],
    "process_chunks": [],
    "regulatory_fp": None,
    "control_fp": None,
    "process_fp": None,
    "phase_1_draft": [],
    "phase_1_approved": [],
    "phase_2_draft": [],
    "phase_2_approved": [],
    "phase_3_draft": [],
    "phase_3_approved": [],
    "phase_1_complete": False,
    "phase_2_complete": False,
    "phase_3_complete": False,
    "phase_1_history": [],
    "phase_2_history": [],
    "phase_3_history": [],
    "verdict": None,
    "current_page": "Upload Documents",
}


def _parse_session_number(session_id: str) -> int | None:
    """Extract session number from ID. Supports sessionN_MMDDHHMM and legacy session_id_MMDD_HHMM_sessionN."""
    if not session_id:
        return None
    # New format: session1_03152246
    m = re.match(r"^session(\d+)_", session_id)
    if m:
        return int(m.group(1))
    # Legacy: session_id_0315_2246_session1
    m = re.search(r"_session(\d+)$", session_id)
    if m:
        return int(m.group(1))
    return None


def _next_session_number() -> int:
    """Return the next sequential session number (session1, session2, session3, ...).
    Ensures the number is always greater than any existing session to avoid duplicates.
    """
    current = st.session_state.get("session_counter", 0) + 1
    order = st.session_state.get("session_order", [])
    existing = [_parse_session_number(sid) for sid in order]
    existing = [n for n in existing if n is not None]
    candidate = max(current, (max(existing) + 1) if existing else 1)
    st.session_state["session_counter"] = candidate
    return candidate


def _new_session_id(session_number: int) -> str:
    """Return a readable, sortable session ID: sessionN_MMDDHHMM (e.g. session1_03152246)."""
    now = datetime.now()
    return f"session{session_number}_{now.strftime('%m%d')}{now.strftime('%H%M')}"


def _snapshot() -> dict:
    """Capture current flat session_state keys into a dict."""
    return {k: st.session_state.get(k) for k in SESSION_KEYS}


def _restore(data: dict):
    """Load a session snapshot back into flat session_state keys."""
    for k in SESSION_KEYS:
        if k in data:
            st.session_state[k] = data[k]
        elif k in DEFAULTS:
            st.session_state[k] = DEFAULTS[k]


def init_sessions():
    """Initialize session management on first load."""
    if "sessions" not in st.session_state:
        st.session_state["session_counter"] = 0
        num = _next_session_number()
        first_id = _new_session_id(num)
        st.session_state["sessions"] = {}
        st.session_state["session_names"] = {}
        st.session_state["active_session_id"] = first_id
        st.session_state["session_order"] = [first_id]

        for k, v in DEFAULTS.items():
            if k not in st.session_state:
                st.session_state[k] = v

        # Default display name = session ID (e.g. session1_03152246) so it's recognizable in sidebar and History without renaming
        st.session_state["session_names"][first_id] = first_id
        st.session_state["sessions"][first_id] = _snapshot()


def create_session(name: str | None = None) -> str:
    """Create a new session, save current one, switch to the new one."""
    _save_current()

    num = _next_session_number()
    new_id = _new_session_id(num)
    # Default display name = session ID (e.g. session2_03152246) so it's recognizable until renamed
    display_name = name if name else new_id

    st.session_state["session_names"][new_id] = display_name
    st.session_state["session_order"].append(new_id)

    _restore(DEFAULTS)
    st.session_state["sessions"][new_id] = _snapshot()
    st.session_state["active_session_id"] = new_id

    return new_id


def switch_session(session_id: str):
    """Save current session and switch to another."""
    current = st.session_state.get("active_session_id")
    if session_id == current:
        return

    _save_current()

    data = st.session_state["sessions"].get(session_id, DEFAULTS)
    _restore(data)
    st.session_state["active_session_id"] = session_id


def _save_current():
    """Persist current flat keys into the sessions store."""
    current = st.session_state.get("active_session_id")
    if current:
        st.session_state["sessions"][current] = _snapshot()


def rename_session(session_id: str, new_name: str):
    """Rename an existing session."""
    st.session_state["session_names"][session_id] = new_name


def delete_session(session_id: str):
    """Delete a session. Cannot delete the last remaining session."""
    order = st.session_state["session_order"]
    if len(order) <= 1:
        return

    order.remove(session_id)
    st.session_state["sessions"].pop(session_id, None)
    st.session_state["session_names"].pop(session_id, None)

    if st.session_state["active_session_id"] == session_id:
        new_active = order[0]
        data = st.session_state["sessions"].get(new_active, DEFAULTS)
        _restore(data)
        st.session_state["active_session_id"] = new_active


def get_session_list() -> list[tuple[str, str]]:
    """Return [(session_id, display_name), ...] in creation order."""
    order = st.session_state.get("session_order", [])
    names = st.session_state.get("session_names", {})
    return [(sid, names.get(sid, sid)) for sid in order]


def get_active_id() -> str:
    return st.session_state.get("active_session_id", "")


def get_session_output_dir():
    """Return a session-scoped output directory path."""
    from config import OUTPUTS_DIR
    active = get_active_id()
    session_dir = OUTPUTS_DIR / active
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def get_session_uploads_dir():
    """Return a session-scoped uploads directory so each session's files stay separate."""
    from config import UPLOADS_DIR
    active = get_active_id()
    if not active:
        return None
    upload_dir = UPLOADS_DIR / active
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_download_prefix() -> str:
    """Return a filename-safe prefix like 'session1' for download files."""
    import re
    active = get_active_id()
    names = st.session_state.get("session_names", {})
    name = names.get(active, active)
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return safe or active


def write_session_meta():
    """Write a meta.json to the session output folder for the history page.
    Uses only approved phase data and verdict; never writes feedback history or agent_message.
    """
    import json
    active = get_active_id()
    names = st.session_state.get("session_names", {})
    session_name = names.get(active, active)

    p1 = st.session_state.get("phase_1_approved", [])
    p2 = st.session_state.get("phase_2_approved", [])
    p3 = st.session_state.get("phase_3_approved", [])

    meta = {
        "session_id": active,
        "session_name": session_name,
        "updated_at": datetime.now().isoformat(),
        "phases_complete": {
            "phase_1": st.session_state.get("phase_1_complete", False),
            "phase_2": st.session_state.get("phase_2_complete", False),
            "phase_3": st.session_state.get("phase_3_complete", False),
        },
        "counts": {
            "risks": len(p1),
            "controls": len(set(r.get("control_id", "") for r in p2)),
            "control_mappings": len(p2),
            "processes": len(set(r.get("process_name", "") for r in p3)),
            "process_mappings": len(p3),
        },
        "has_verdict": st.session_state.get("verdict") is not None,
    }

    out_dir = get_session_output_dir()
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def save_on_action():
    """Call after any state-modifying action to keep the session store in sync."""
    _save_current()
    write_session_meta()

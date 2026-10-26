"""Streamlit entry: sidebar, sessions, and page routing for the Risk Governance Agent."""

import streamlit as st
from ui.styles import inject_css
from ui.session_manager import (
    init_sessions,
    create_session,
    switch_session,
    rename_session,
    delete_session,
    get_session_list,
    get_active_id,
    save_on_action,
)

st.set_page_config(
    page_title="Risk Governance Agent",
    page_icon="🛡️",
    layout="wide",
)

inject_css()
init_sessions()

# ---- Sidebar ----
with st.sidebar:
    st.markdown("### 🛡️ Risk Governance Agent")

    # ---- Session selector ----
    sessions = get_session_list()
    active_id = get_active_id()

    session_labels = {sid: name for sid, name in sessions}
    session_ids = [sid for sid, _ in sessions]
    active_idx = session_ids.index(active_id) if active_id in session_ids else 0

    # Session switcher (index=active_idx keeps display in sync with active session; do not set session_selector in state to avoid widget conflict)
    col_sel, col_new = st.columns([3, 1])
    with col_sel:
        selected = st.selectbox(
            "Active Session",
            options=session_ids,
            index=active_idx,
            format_func=lambda sid: session_labels.get(sid, sid),
            key="session_selector",
        )
    with col_new:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("＋ New", key="new_session_btn", help="Create new session", use_container_width=True):
            create_session()
            st.session_state.pop("session_selector", None)
            st.session_state["editing_session_name"] = False
            st.rerun()

    if selected != active_id:
        switch_session(selected)
        st.rerun()

    # Session name display + edit toggle
    current_name = session_labels.get(active_id, "")
    editing = st.session_state.get("editing_session_name", False)

    if editing:
        new_name = st.text_input(
            "New session name",
            value=current_name,
            key=f"rename_input_{active_id}",
        )
        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save", key="save_rename_btn", type="primary", use_container_width=True):
                if new_name and new_name != current_name:
                    rename_session(active_id, new_name)
                    save_on_action()
                st.session_state["editing_session_name"] = False
                st.rerun()
        with col_cancel:
            if st.button("Cancel", key="cancel_rename_btn", use_container_width=True):
                st.session_state["editing_session_name"] = False
                st.rerun()
    else:
        st.markdown(f"**{current_name}**")
        col_edit, col_del = st.columns(2)
        with col_edit:
            if st.button("✏️ Rename", key="edit_session_btn", use_container_width=True):
                st.session_state["editing_session_name"] = True
                st.rerun()
        with col_del:
            if len(sessions) > 1:
                if st.button("🗑️ Delete", key="delete_session_btn", type="secondary", use_container_width=True):
                    delete_session(active_id)
                    st.session_state.pop("session_selector", None)
                    st.session_state["editing_session_name"] = False
                    st.rerun()

    st.markdown("---")

    # ---- Progress ----
    phases_done = sum([
        st.session_state.get("phase_1_complete", False),
        st.session_state.get("phase_2_complete", False),
        st.session_state.get("phase_3_complete", False),
    ])
    progress_pct = int(phases_done / 3 * 100)

    st.caption(f"Progress: {phases_done}/3 phases complete")
    st.markdown(
        f'<div class="progress-track">'
        f'<div class="progress-fill" style="width:{progress_pct}%"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ---- Navigation steps (each is a single clickable button) ----
    has_docs = bool(
        st.session_state.get("regulatory_files")
        or st.session_state.get("control_files")
        or st.session_state.get("process_files")
    )
    p1_done = st.session_state.get("phase_1_complete", False)
    p2_done = st.session_state.get("phase_2_complete", False)
    p3_done = st.session_state.get("phase_3_complete", False)

    reg_n = len(st.session_state.get("regulatory_files", []))
    ctrl_n = len(st.session_state.get("control_files", []))
    proc_n = len(st.session_state.get("process_files", []))

    steps = [
        ("Upload Documents", "📄", f"{reg_n}R / {ctrl_n}C / {proc_n}P", False),
        ("Phase 1 – Risks", "✅" if p1_done else "1️⃣",
         f"{len(st.session_state.get('phase_1_approved', []))} risks" if p1_done else "Extract risks",
         not st.session_state.get("regulatory_chunks")),
        ("Phase 2 – Controls", "✅" if p2_done else "2️⃣",
         f"{len(st.session_state.get('phase_2_approved', []))} mappings" if p2_done else "Map to controls",
         not p1_done),
        ("Phase 3 – Processes", "✅" if p3_done else "3️⃣",
         f"{len(st.session_state.get('phase_3_approved', []))} mappings" if p3_done else "Map to processes",
         not p2_done),
        ("Summary", "📊", "Review register", not p1_done),
        ("History", "🗂️", "Past outputs", False),
    ]

    current_page = st.session_state.get("current_page", "Upload Documents")

    for key, icon, sub, locked in steps:
        is_active = current_page == key
        if locked:
            st.markdown(
                f'<div class="step locked">'
                f'<span class="step-icon">{icon}</span>'
                f'<div class="step-text">'
                f'<div class="step-title">{key}</div>'
                f'<div class="step-sub">{sub}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        else:
            btn_type = "primary" if is_active else "tertiary"
            if st.button(
                f"{icon}  {key}",
                key=f"nav_{key}",
                use_container_width=True,
                type=btn_type,
            ):
                st.session_state["current_page"] = key
                save_on_action()
                st.rerun()
            if sub:
                st.caption(f"    {sub}")

    st.markdown("---")
    st.caption("Powered by Ollama + Gemma 2 (small version)")
    if st.button("⏹ Shutdown Server", key="shutdown_btn", use_container_width=True):
        st.warning("Server shutting down...")
        import os
        os._exit(0)

# ---- Page routing ----
page = st.session_state.get("current_page", "Upload Documents")

if page == "Upload Documents":
    from ui.upload_page import render
    render()
elif page == "Phase 1 – Risks":
    from ui.phase_1_page import render
    render()
elif page == "Phase 2 – Controls":
    from ui.phase_2_page import render
    render()
elif page == "Phase 3 – Processes":
    from ui.phase_3_page import render
    render()
elif page == "Summary":
    from ui.summary_page import render
    render()
elif page == "History":
    from ui.history_page import render
    render()

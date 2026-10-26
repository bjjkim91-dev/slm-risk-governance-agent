"""Phase 3 page: map controls to processes, agent-driven feedback loop, approve."""

import copy
import json
import re
import streamlit as st

from phases.phase_3 import run_phase_3
from prompts.feedback import (
    build_phase_3_feedback_prompt,
    feedback_needs_source_phase3,
    parse_note_feedback,
    parse_process_assignment_p3,
)
from llm_client import generate_json, get_model, swap_model
from schemas import make_row_id
from config import CONTROL_PROCESS_MAPPING_PREFIX, MAX_OUTPUT_TOKENS_FEEDBACK
from ui.styles import phase_banner, metric_row, html_table
from ui.session_manager import save_on_action, get_session_output_dir, get_download_prefix
from ui.exporters import build_excel, build_pdf

# Index is 1-based row number; column header "Row #" = Index for feedback
_P3_COLUMNS = [
    ("Index", "Row #", "col-id"),
    ("control_id", "Control ID", "col-id"),
    ("control_description", "Control Description", "col-xl"),
    ("process_id", "Process ID", "col-id"),
    ("process_name", "Process Step", "col-lg"),
    ("process_step", "Process Detail", "col-lg"),
    ("why_process_assigned", "Rationale", "col-xl"),
    ("Comment", "Comment", "col-md"),
    ("user_status", "Status", "col-sm"),
]


def _reassign_mapping_ids(mappings: list[dict]) -> list[dict]:
    for i, m in enumerate(mappings, start=1):
        m["control_process_mapping_id"] = make_row_id(CONTROL_PROCESS_MAPPING_PREFIX, i)
    return mappings


def _apply_feedback_fix_p3(
    draft: list[dict], revised: list[dict], feedback: str, approved_rc: list[dict] | None = None
) -> list[dict]:
    """Apply delete, process assignment, or note/comment when the model didn't; update Comment (feedback/user_notes)."""
    if not draft or not revised:
        return revised
    fb = feedback.strip().lower()
    n_draft = len(draft)
    n_rev = len(revised)

    # Assign index N to process Px, Process Name (index = table Row #, including placeholders)
    assignment = parse_process_assignment_p3(feedback)
    if assignment:
        idx, process_id, process_name = assignment
        display = _build_p3_display_rows(revised, approved_rc or [])
        if 1 <= idx <= len(display):
            row = display[idx - 1]
            if row.get("process_name") == "(Not assigned)":
                # Add new mapping for this control
                new_mapping = {
                    "control_process_mapping_id": "",
                    "control_id": row.get("control_id", ""),
                    "control_description": row.get("control_description", ""),
                    "process_id": process_id,
                    "process_name": process_name,
                    "process_step": "",
                    "why_process_assigned": "Assigned per user feedback.",
                    "user_status": "Edited",
                    "user_notes": "",
                    "feedback": "",
                }
                revised = copy.deepcopy(revised) + [new_mapping]
                return _reassign_mapping_ids(revised)
            # Update existing mapping at this index
            if idx <= n_rev:
                revised = copy.deepcopy(revised)
                revised[idx - 1]["process_id"] = process_id
                revised[idx - 1]["process_name"] = process_name
                revised[idx - 1]["user_status"] = "Edited"
                return revised
        # index out of range; fall through to other parsers

    # Delete index N
    m = re.search(r"(?:delete|remove)\s+index\s+(\d+)|index\s+(\d+)\s+(?:delete|remove)", fb)
    if m:
        idx = int(m.group(1) or m.group(2))
        if 1 <= idx <= n_draft and n_rev == n_draft:
            revised = [r for i, r in enumerate(draft, 1) if i != idx]
            return _reassign_mapping_ids(revised)

    # Note/comment for index (shared parser) — only when feedback looks like a note, not an assignment
    if not assignment:
        idx, note = parse_note_feedback(feedback)
        if idx is not None and note and 1 <= idx <= n_rev:
            revised = copy.deepcopy(revised)
            revised[idx - 1]["feedback"] = note
            revised[idx - 1]["user_notes"] = note
            revised[idx - 1]["user_status"] = "Edited"
    return revised


def _build_p3_display_rows(draft: list[dict], approved_rc: list[dict]) -> list[dict]:
    """Draft mappings plus one placeholder row per control that has no process (informative)."""
    display = list(draft)
    p3_control_ids = {m.get("control_id", "") for m in draft}
    # P2 may have same control for multiple risks; get unique controls and first occurrence for description
    p2_by_cid = {}
    for m in approved_rc or []:
        cid = m.get("control_id", "")
        if cid and cid not in p2_by_cid:
            p2_by_cid[cid] = m
    for cid, m in p2_by_cid.items():
        if cid not in p3_control_ids:
            display.append({
                "control_process_mapping_id": "",
                "risk_control_mapping_id": m.get("risk_control_mapping_id", ""),
                "control_id": cid,
                "control_description": m.get("control_description", ""),
                "process_id": "",
                "process_name": "(Not assigned)",
                "process_step": "",
                "why_process_assigned": "",
                "user_status": "Unassigned",
                "user_notes": "",
                "feedback": "",
            })
    return display


def _styled_dataframe(draft: list[dict]):
    rows = []
    for i, r in enumerate(draft, 1):
        row = dict(r)
        row["Index"] = i
        row["Comment"] = str(row.get("feedback") or row.get("user_notes") or "").strip()
        rows.append(row)
    cols = [(k, l, s) for k, l, s in _P3_COLUMNS if k == "Index" or k == "Comment" or any(k in r for r in rows)]
    st.markdown(html_table(rows, cols), unsafe_allow_html=True)


def _render_history(history: list[dict]):
    if len(history) <= 1:
        return
    with st.expander(f"📝 Revision History ({len(history)} versions)"):
        for entry in reversed(history):
            v = entry["version"]
            src = entry["source"]
            count = len(entry["data"])
            if src == "model":
                st.markdown(
                    f'<div class="timeline-entry"><span class="timeline-dot"></span>'
                    f'<strong>v{v}</strong> — Initial mapping ({count} mappings)</div>',
                    unsafe_allow_html=True,
                )
            else:
                fb = entry.get("feedback", "")
                msg = entry.get("agent_message", "")
                line = f'<strong>v{v}</strong> — Feedback: <em>"{fb}"</em> → {count} mappings'
                if msg:
                    line += f'<br><span style="opacity:0.85;">Agent: {msg}</span>'
                st.markdown(
                    f'<div class="timeline-entry"><span class="timeline-dot"></span>{line}</div>',
                    unsafe_allow_html=True,
                )


def render():
    st.markdown(
        phase_banner(
            "Phase 3 – Control to Process Mapping",
            "Map each control to the business process that implements it.",
            "⚙️",
        ),
        unsafe_allow_html=True,
    )

    approved_rc = st.session_state.get("phase_2_approved", [])
    process_chunks = st.session_state.get("process_chunks", [])

    if not approved_rc:
        st.warning("Phase 2 not complete. Approve risk-control mappings in **Phase 2** first.")
        return
    if not process_chunks:
        st.warning("No process documents uploaded. Go to **Upload Documents** first.")
        return

    already_approved = st.session_state.get("phase_3_complete", False)

    st.info(
        f"📄 {len(approved_rc)} risk-control pair(s) · {len(process_chunks)} process chunk(s) ready."
    )

    if not already_approved:
        if st.button("Run Phase 3 – Map Controls to Processes", type="primary"):
            with st.spinner("Calling local model to map controls to processes..."):
                results = run_phase_3(approved_rc, process_chunks)
            st.session_state["phase_3_draft"] = results
            st.session_state["phase_3_approved"] = []
            st.session_state["phase_3_complete"] = False
            st.session_state["phase_3_history"] = [
                {"version": 0, "source": "model", "data": results}
            ]
            save_on_action()
            st.rerun()

    draft = st.session_state.get("phase_3_draft", [])
    display_list = _build_p3_display_rows(draft, approved_rc)
    if not display_list:
        return

    # ---- Metrics (from actual mappings only) ----
    unique_controls = len(set(r.get("control_id", "") for r in draft))
    unique_processes = len(set(r.get("process_name", "") for r in draft))

    st.markdown(
        metric_row([
            (unique_controls, "Controls"),
            (unique_processes, "Processes"),
            (len(draft), "Mappings"),
        ]),
        unsafe_allow_html=True,
    )

    st.markdown("#### Current Governance Map")
    st.caption("Controls with no process show \"(Not assigned)\" — assign a process in feedback or re-run Phase 3.")
    with st.container(key=f"p3_table_{st.session_state.get('phase_3_feedback_key', 0)}"):
        _styled_dataframe(display_list)

    if already_approved:
        st.markdown("---")
        st.success(f"✓ Phase 3 approved — {len(draft)} mapping(s)")
        col1, col2, col3 = st.columns([2, 2, 3])
        prefix = get_download_prefix()
        p3_data = st.session_state["phase_3_approved"]
        with col1:
            st.download_button(
                "📥 Excel",
                data=build_excel(p3=p3_data),
                file_name=f"{prefix}_governance_map.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col2:
            st.download_button(
                "📥 PDF",
                data=build_pdf(p3=p3_data, session_name=prefix),
                file_name=f"{prefix}_governance_map.pdf",
                mime="application/pdf",
            )
        with col3:
            if st.button("Continue to Summary →", type="primary"):
                st.session_state["current_page"] = "Summary"
                st.rerun()

        _render_history(st.session_state.get("phase_3_history", []))
        return

    # ---- Feedback (only shown before approval) ----
    if st.session_state.get("phase_3_feedback_message"):
        msg = st.session_state.pop("phase_3_feedback_message", "")
        st.success(msg + (" Review the table above." if msg else "Table updated above."))

    st.markdown(
        '<div class="feedback-box">'
        '<div class="card-header">💬 Provide Feedback</div>'
        '<p style="font-size:0.85rem; opacity:0.7; margin-bottom:0.5rem;">'
        'Always use <strong>Index</strong> (Row #) in feedback: name the index, then the change (e.g. <em>Index 5 assign to P9, Employee Training</em> for unassigned controls, <em>Index 7 delete</em>). Add or remove mappings as needed.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    feedback_text = st.text_area(
        "Your feedback",
        placeholder='e.g. "Index 5 assign to P9, Employee Training" or "Index 7 delete"',
        key=f"phase_3_feedback_input_{st.session_state.get('phase_3_feedback_key', 0)}",
        label_visibility="visible",
        height=120,
    )

    col_fb1, col_fb2 = st.columns([1, 4])
    with col_fb1:
        apply_clicked = st.button("Apply Feedback", disabled=not feedback_text, key="p3_apply")

    if apply_clicked:
        with st.spinner("Updating governance map..."):
            process_chunks = st.session_state.get("process_chunks", []) if feedback_needs_source_phase3(feedback_text) else None
            prompt = build_phase_3_feedback_prompt(draft, feedback_text, process_chunks=process_chunks)
            try:
                raw = generate_json(
                    prompt, model=get_model("phase_3"),
                    max_tokens=MAX_OUTPUT_TOKENS_FEEDBACK,
                )
                if isinstance(raw, dict) and "data" in raw:
                    revised = raw["data"]
                    agent_message = raw.get("message", "")
                else:
                    revised = raw if isinstance(raw, list) else [raw]
                    agent_message = ""
                if isinstance(revised, dict):
                    revised = [revised]
                for m in revised:
                    m.pop("Index", None)
                revised = _reassign_mapping_ids(revised)
                approved_rc = st.session_state.get("phase_2_approved", [])
                revised = _apply_feedback_fix_p3(draft, revised, feedback_text, approved_rc)

                history = st.session_state.get("phase_3_history", [])
                history.append({
                    "version": len(history),
                    "source": "user_feedback",
                    "feedback": feedback_text,
                    "agent_message": agent_message,
                    "data": list(revised),
                })
                st.session_state["phase_3_history"] = history
                st.session_state["phase_3_draft"] = copy.deepcopy(revised)
                st.session_state["phase_3_feedback_message"] = agent_message
                st.session_state["phase_3_feedback_key"] = st.session_state.get("phase_3_feedback_key", 0) + 1
                save_on_action()
                st.rerun()
            except (ValueError, ConnectionError) as e:
                st.error(f"Failed to apply feedback: {e}")

    _render_history(st.session_state.get("phase_3_history", []))

    # ---- Approve ----
    st.markdown("---")
    if st.button("Approve & Save ✓", type="primary", key="p3_approve"):
        st.session_state["phase_3_approved"] = draft
        st.session_state["phase_3_complete"] = True

        # Persist only the approved mapping list; feedback history and agent_message are not saved.
        out_path = get_session_output_dir() / "phase_3_approved.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, indent=2)
        save_on_action()
        swap_model("phase_3", "summary")
        st.rerun()

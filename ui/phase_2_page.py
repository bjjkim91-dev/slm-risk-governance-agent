"""Phase 2 page: map risks to controls, agent-driven feedback loop, approve."""

import copy
import json
import re
import streamlit as st

from phases.phase_2 import run_phase_2
from prompts.feedback import (
    build_phase_2_feedback_prompt,
    feedback_needs_source_phase2,
    parse_note_feedback,
    parse_field_updates_p2,
)
from llm_client import generate_json, get_model, swap_model
from schemas import make_row_id
from config import RISK_CONTROL_MAPPING_PREFIX, MAX_OUTPUT_TOKENS_FEEDBACK
from ui.styles import phase_banner, metric_row, html_table
from ui.session_manager import save_on_action, get_session_output_dir, get_download_prefix
from ui.exporters import build_excel, build_pdf

# Index is 1-based row number; column header "Row #" = Index for feedback
_P2_COLUMNS = [
    ("Index", "Row #", "col-id"),
    ("risk_id", "Risk ID", "col-id"),
    ("risk_statement", "Risk", "col-xl"),
    ("control_id", "Control ID", "col-id"),
    ("control_description", "Control Description", "col-xl"),
    ("why_control_assigned", "Rationale", "col-xl"),
    ("control_type", "Type", "col-sm"),
    ("execution_type", "Execution", "col-sm"),
    ("Comment", "Comment", "col-md"),
    ("user_status", "Status", "col-sm"),
]


def _reassign_mapping_ids(mappings: list[dict]) -> list[dict]:
    for i, m in enumerate(mappings, start=1):
        m["risk_control_mapping_id"] = make_row_id(RISK_CONTROL_MAPPING_PREFIX, i)
    return mappings


def _apply_feedback_fix_p2(draft: list[dict], revised: list[dict], feedback: str) -> list[dict]:
    """Apply delete, field updates (e.g. execution type), or note/comment when the model didn't."""
    if not draft or not revised:
        return revised
    revised = copy.deepcopy(revised)
    fb = feedback.strip().lower()
    n_draft = len(draft)
    n_rev = len(revised)

    # Delete index N
    m = re.search(r"(?:delete|remove)\s+index\s+(\d+)|index\s+(\d+)\s+(?:delete|remove)", fb)
    if m:
        idx = int(m.group(1) or m.group(2))
        if 1 <= idx <= n_draft and n_rev == n_draft:
            revised = [r for i, r in enumerate(revised, 1) if i != idx]
            return _reassign_mapping_ids(revised)

    # Field updates: "index 14 change execution type to Automated" -> set field and store a short comment
    for idx, field, value in parse_field_updates_p2(feedback):
        if 1 <= idx <= n_rev and field in ("execution_type", "control_type"):
            revised[idx - 1][field] = value
            revised[idx - 1]["user_status"] = "Edited"
            revised[idx - 1]["user_notes"] = f"Changed {field.replace('_', ' ')} to {value}"
            revised[idx - 1]["feedback"] = revised[idx - 1]["user_notes"]

    # Note/comment for index (e.g. "index 14 note: Changed execution type to Automated")
    idx, note = parse_note_feedback(feedback)
    if idx is not None and note and 1 <= idx <= n_rev:
        revised[idx - 1]["feedback"] = note
        revised[idx - 1]["user_notes"] = note
        revised[idx - 1]["user_status"] = "Edited"
    return revised


def _build_p2_display_rows(draft: list[dict], approved_risks: list[dict]) -> list[dict]:
    """Draft mappings plus one placeholder row per approved risk that has no control (informative)."""
    display = list(draft)
    risk_ids_with_control = {m.get("risk_id", "") for m in draft}
    for r in approved_risks:
        rid = r.get("risk_id", "")
        if rid and rid not in risk_ids_with_control:
            display.append({
                "risk_control_mapping_id": "",
                "input_risk_mapping_id": r.get("input_risk_mapping_id", ""),
                "risk_id": rid,
                "risk_statement": r.get("risk_statement", ""),
                "control_id": "",
                "control_description": "(Not assigned)",
                "why_control_assigned": "",
                "control_type": "",
                "execution_type": "",
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
    cols = [(k, l, s) for k, l, s in _P2_COLUMNS if k == "Index" or k == "Comment" or any(k in r for r in rows)]
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
            "Phase 2 – Risk to Control Mapping",
            "Map each approved risk to mitigating controls from your control documents.",
            "🔗",
        ),
        unsafe_allow_html=True,
    )

    approved_risks = st.session_state.get("phase_1_approved", [])
    control_chunks = st.session_state.get("control_chunks", [])

    if not approved_risks:
        st.warning("Phase 1 not complete. Approve risks in **Phase 1** first.")
        return
    if not control_chunks:
        st.warning("No control documents uploaded. Go to **Upload Documents** first.")
        return

    already_approved = st.session_state.get("phase_2_complete", False)

    st.info(
        f"📄 {len(approved_risks)} approved risk(s) · {len(control_chunks)} control chunk(s) ready."
    )

    if not already_approved:
        if st.button("Run Phase 2 – Map Risks to Controls", type="primary"):
            with st.spinner("Calling local model to map risks to controls..."):
                results = run_phase_2(approved_risks, control_chunks)
            st.session_state["phase_2_draft"] = results
            st.session_state["phase_2_approved"] = []
            st.session_state["phase_2_complete"] = False
            st.session_state["phase_2_history"] = [
                {"version": 0, "source": "model", "data": results}
            ]
            save_on_action()
            st.rerun()

    draft = st.session_state.get("phase_2_draft", [])
    display_list = _build_p2_display_rows(draft, approved_risks)
    if not display_list:
        return

    # ---- Metrics (from actual mappings only) ----
    unique_risks = len(set(r.get("risk_id", "") for r in draft))
    unique_controls = len(set(r.get("control_id", "") for r in draft))
    type_counts = {}
    for r in draft:
        t = r.get("control_type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    st.markdown(
        metric_row([
            (unique_risks, "Risks"),
            (unique_controls, "Controls"),
            (len(draft), "Mappings"),
            (type_counts.get("Preventive", 0), "Preventive"),
        ]),
        unsafe_allow_html=True,
    )

    st.markdown("#### Current Risk-Control Matrix")
    st.caption("Risks with no control show \"(Not assigned)\" — assign a control in feedback or re-run Phase 2.")
    with st.container(key=f"p2_table_{st.session_state.get('phase_2_feedback_key', 0)}"):
        _styled_dataframe(display_list)

    if already_approved:
        st.markdown("---")
        st.success(f"✓ Phase 2 approved — {len(draft)} mapping(s)")
        col1, col2, col3 = st.columns([2, 2, 3])
        prefix = get_download_prefix()
        p2_data = st.session_state["phase_2_approved"]
        with col1:
            st.download_button(
                "📥 Excel",
                data=build_excel(p2=p2_data),
                file_name=f"{prefix}_risk_control_matrix.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col2:
            st.download_button(
                "📥 PDF",
                data=build_pdf(p2=p2_data, session_name=prefix),
                file_name=f"{prefix}_risk_control_matrix.pdf",
                mime="application/pdf",
            )
        with col3:
            if st.button("Continue to Phase 3 →", type="primary"):
                st.session_state["current_page"] = "Phase 3 – Processes"
                st.rerun()

        _render_history(st.session_state.get("phase_2_history", []))
        return

    # ---- Feedback (only shown before approval) ----
    if st.session_state.get("phase_2_feedback_message"):
        msg = st.session_state.pop("phase_2_feedback_message", "")
        st.success(msg + (" Review the table above." if msg else "Table updated above."))

    st.markdown(
        '<div class="feedback-box">'
        '<div class="card-header">💬 Provide Feedback</div>'
        '<p style="font-size:0.85rem; opacity:0.7; margin-bottom:0.5rem;">'
        'Always use <strong>Index</strong> (Row #) in feedback: name the index, then the change (e.g. <em>Index 2 change control_type to Detective</em>, <em>Index 5 delete</em>). Add or remove mappings as needed.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    feedback_text = st.text_area(
        "Your feedback",
        placeholder='e.g. "Index 2 change control_type to Detective" or "Index 5 delete" or "Add a control for RISK-001"',
        key=f"phase_2_feedback_input_{st.session_state.get('phase_2_feedback_key', 0)}",
        label_visibility="visible",
        height=120,
    )

    col_fb1, col_fb2 = st.columns([1, 4])
    with col_fb1:
        apply_clicked = st.button("Apply Feedback", disabled=not feedback_text, key="p2_apply")

    if apply_clicked:
        with st.spinner("Updating mappings..."):
            control_chunks = st.session_state.get("control_chunks", []) if feedback_needs_source_phase2(feedback_text) else None
            prompt = build_phase_2_feedback_prompt(draft, feedback_text, control_chunks=control_chunks)
            try:
                raw = generate_json(
                    prompt, model=get_model("phase_2"),
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
                revised = _apply_feedback_fix_p2(draft, revised, feedback_text)

                history = st.session_state.get("phase_2_history", [])
                history.append({
                    "version": len(history),
                    "source": "user_feedback",
                    "feedback": feedback_text,
                    "agent_message": agent_message,
                    "data": list(revised),
                })
                st.session_state["phase_2_history"] = history
                st.session_state["phase_2_draft"] = copy.deepcopy(revised)
                st.session_state["phase_2_feedback_message"] = agent_message
                st.session_state["phase_2_feedback_key"] = st.session_state.get("phase_2_feedback_key", 0) + 1
                save_on_action()
                st.rerun()
            except (ValueError, ConnectionError) as e:
                st.error(f"Failed to apply feedback: {e}")

    _render_history(st.session_state.get("phase_2_history", []))

    # ---- Approve ----
    st.markdown("---")
    if st.button("Approve & Save ✓", type="primary", key="p2_approve"):
        st.session_state["phase_2_approved"] = draft
        st.session_state["phase_2_complete"] = True

        # Persist only the approved mapping list; feedback history and agent_message are not saved.
        out_path = get_session_output_dir() / "phase_2_approved.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, indent=2)
        save_on_action()
        swap_model("phase_2", "phase_3")
        st.rerun()

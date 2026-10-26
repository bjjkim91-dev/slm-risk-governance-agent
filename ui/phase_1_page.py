"""Phase 1 page: extract risks, agent-driven feedback loop, approve."""

import copy
import json
import re
import streamlit as st

from phases.phase_1 import run_phase_1
from prompts.feedback import build_phase_1_feedback_prompt, feedback_needs_source_phase1, parse_note_feedback
from llm_client import generate_json, get_model, swap_model
from schemas import make_id, make_row_id
from config import RISK_ID_PREFIX, INPUT_RISK_MAPPING_PREFIX, MAX_OUTPUT_TOKENS_FEEDBACK
from ui.styles import phase_banner, metric_row, severity_badge, html_table
from ui.session_manager import save_on_action, get_session_output_dir, get_download_prefix
from ui.exporters import build_excel, build_pdf


def _reassign_ids(risks: list[dict]) -> list[dict]:
    for i, r in enumerate(risks, start=1):
        r["risk_id"] = make_id(RISK_ID_PREFIX, i)
        r["input_risk_mapping_id"] = make_row_id(INPUT_RISK_MAPPING_PREFIX, i)
    return risks


def _apply_feedback_fix_p1(draft: list[dict], revised: list[dict], feedback: str) -> list[dict]:
    """If the model didn't apply an obvious delete or severity change, apply it client-side so the table updates."""
    if not draft or not revised:
        return revised
    fb = feedback.strip().lower()
    n_draft = len(draft)
    n_rev = len(revised)

    # Delete index N: e.g. "delete index 15", "index 15 delete"
    m = re.search(r"(?:delete|remove)\s+index\s+(\d+)|index\s+(\d+)\s+(?:delete|remove)", fb)
    if m:
        idx = int(m.group(1) or m.group(2))
        if 1 <= idx <= n_draft and n_rev == n_draft:
            revised = [r for i, r in enumerate(draft, 1) if i != idx]
            return _reassign_ids(revised)

    # Severity change: e.g. "change index 15 to low severity", "index 15 severity to low"
    m = re.search(r"index\s+(\d+).*?(?:severity\s+to|to)\s+(low|medium|high)", fb)
    if m:
        idx = int(m.group(1))
        sev = {"low": "Low", "medium": "Medium", "high": "High"}.get(m.group(2).lower(), "Low")
        if 1 <= idx <= n_rev and n_rev == n_draft and revised[idx - 1].get("severity") != sev:
            revised = copy.deepcopy(revised)
            revised[idx - 1]["severity"] = sev
            revised[idx - 1]["user_status"] = "Edited"
            revised[idx - 1]["feedback"] = f"Severity updated to {sev}."
            revised[idx - 1]["user_notes"] = revised[idx - 1]["feedback"]

    # Note/comment for index (shared parser)
    idx, note = parse_note_feedback(feedback)
    if idx is not None and note and 1 <= idx <= n_rev:
        revised = copy.deepcopy(revised)
        revised[idx - 1]["feedback"] = note
        revised[idx - 1]["user_notes"] = note
        revised[idx - 1]["user_status"] = "Edited"
    return revised


# risk_id is the canonical row ID; input_risk_mapping_id is kept in data for Phase 2 traceability but not shown
# Index is 1-based row number for user reference; column header shows "Row #" so users know row number = Index
_P1_COLUMNS = [
    ("Index", "Row #", "col-id"),
    ("risk_id", "Risk ID", "col-id"),
    ("requirement_theme", "Theme", "col-sm"),
    ("risk_statement", "Risk Statement", "col-lg"),
    ("why_identified", "Rationale", "col-lg"),
    ("severity", "Severity", "col-sm"),
    ("risk_category", "Category", "col-md"),
    ("source_ref", "Source", "col-sm"),
    ("source_quote", "Quote", "col-xl"),
    ("Comment", "Comment", "col-md"),
    ("user_status", "Status", "col-sm"),
]


def _styled_dataframe(draft: list[dict]):
    """Render the risk table as an HTML table with auto-growing row height."""
    rows = []
    for i, r in enumerate(draft, 1):
        row = dict(r)
        row["Index"] = i
        row["Comment"] = str(row.get("feedback") or row.get("user_notes") or "").strip()
        rows.append(row)
    cols = [(k, l, s) for k, l, s in _P1_COLUMNS if k == "Index" or k == "Comment" or any(k in r for r in rows)]
    st.markdown(html_table(rows, cols), unsafe_allow_html=True)


def _render_history(history: list[dict]):
    """Render revision history as a timeline."""
    if len(history) <= 1:
        return
    with st.expander(f"📝 Revision History ({len(history)} versions)"):
        for entry in reversed(history):
            v = entry["version"]
            src = entry["source"]
            count = len(entry["data"])
            if src == "model":
                st.markdown(
                    f'<div class="timeline-entry">'
                    f'<span class="timeline-dot"></span>'
                    f'<strong>v{v}</strong> — Initial extraction ({count} risks)'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                fb = entry.get("feedback", "")
                msg = entry.get("agent_message", "")
                line = f'<strong>v{v}</strong> — Feedback: <em>"{fb}"</em> → {count} risks'
                if msg:
                    line += f'<br><span style="opacity:0.85;">Agent: {msg}</span>'
                st.markdown(
                    f'<div class="timeline-entry">'
                    f'<span class="timeline-dot"></span>'
                    f'{line}'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def render():
    st.markdown(
        phase_banner(
            "Phase 1 – Risk Extraction",
            "Extract compliance risks from regulatory documents using COSO framework analysis.",
            "🔍",
        ),
        unsafe_allow_html=True,
    )

    chunks = st.session_state.get("regulatory_chunks", [])
    if not chunks:
        st.warning("No regulatory documents uploaded. Go to **Upload Documents** first.")
        return

    already_approved = st.session_state.get("phase_1_complete", False)

    n_chunks = len(chunks)
    st.info(f"📄 {n_chunks} chunk(s) ready from regulatory documents. Phase 1 runs one model call per chunk (no file re-read).")

    if not already_approved:
        if st.button("Run Phase 1 – Extract Risks", type="primary"):
            progress_placeholder = st.empty()
            progress_bar = st.progress(0.0)
            try:
                def on_chunk_done(current: int, total: int):
                    progress_bar.progress(current / total)
                    progress_placeholder.caption(f"Processing chunk {current} of {total}…")

                results = run_phase_1(chunks, progress_callback=on_chunk_done)
            finally:
                progress_bar.empty()
                progress_placeholder.empty()

            st.session_state["phase_1_draft"] = results
            st.session_state["phase_1_approved"] = []
            st.session_state["phase_1_complete"] = False
            st.session_state["phase_1_history"] = [
                {"version": 0, "source": "model", "data": results}
            ]
            save_on_action()
            st.rerun()

    draft = st.session_state.get("phase_1_draft", [])
    if not draft:
        return

    # ---- Metrics ----
    severity_counts = {}
    for r in draft:
        s = r.get("severity", "Unknown")
        severity_counts[s] = severity_counts.get(s, 0) + 1

    st.markdown(
        metric_row([
            (len(draft), "Total Risks"),
            (severity_counts.get("High", 0), "High"),
            (severity_counts.get("Medium", 0), "Medium"),
            (severity_counts.get("Low", 0), "Low"),
        ]),
        unsafe_allow_html=True,
    )

    # ---- Data table (always show latest draft; key forces refresh after feedback) ----
    draft = st.session_state.get("phase_1_draft", [])
    if not draft:
        return
    st.markdown("#### Current Risk Register")
    with st.container(key=f"p1_table_{st.session_state.get('phase_1_feedback_key', 0)}"):
        _styled_dataframe(draft)

    if already_approved:
        # Show approved state: downloads + continue
        st.markdown("---")
        st.success(f"✓ Phase 1 approved — {len(draft)} risk(s)")
        col1, col2, col3 = st.columns([2, 2, 3])
        prefix = get_download_prefix()
        p1_data = st.session_state["phase_1_approved"]
        with col1:
            st.download_button(
                "📥 Excel",
                data=build_excel(p1=p1_data),
                file_name=f"{prefix}_risk_register.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col2:
            st.download_button(
                "📥 PDF",
                data=build_pdf(p1=p1_data, session_name=prefix),
                file_name=f"{prefix}_risk_register.pdf",
                mime="application/pdf",
            )
        with col3:
            if st.button("Continue to Phase 2 →", type="primary"):
                st.session_state["current_page"] = "Phase 2 – Controls"
                st.rerun()

        _render_history(st.session_state.get("phase_1_history", []))
        return

    # ---- Feedback (only shown before approval) ----
    if st.session_state.get("phase_1_feedback_message"):
        msg = st.session_state.pop("phase_1_feedback_message", "")
        st.success(msg + (" Review the table above." if msg else "Table updated above."))

    st.markdown(
        '<div class="feedback-box">'
        '<div class="card-header">💬 Provide Feedback</div>'
        '<p style="font-size:0.85rem; opacity:0.7; margin-bottom:0.5rem;">'
        'Always use <strong>Index</strong> (Row #) in feedback: name the index, then the change (e.g. <em>Index 1 delete</em>, <em>Index 3 update severity to High</em>).</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    feedback_text = st.text_area(
        "Your feedback",
        placeholder='e.g. "Index 1 delete" or "Index 3 update severity to High" or "Add a risk about data retention"',
        key=f"phase_1_feedback_input_{st.session_state.get('phase_1_feedback_key', 0)}",
        label_visibility="visible",
        height=120,
    )

    col_fb1, col_fb2 = st.columns([1, 4])
    with col_fb1:
        apply_clicked = st.button(
            "Apply Feedback", disabled=not feedback_text, type="secondary"
        )

    if apply_clicked:
        with st.spinner("Updating risks..."):
            chunks = st.session_state.get("regulatory_chunks", []) if feedback_needs_source_phase1(feedback_text) else None
            prompt = build_phase_1_feedback_prompt(draft, feedback_text, source_chunks=chunks)
            try:
                raw = generate_json(
                    prompt, model=get_model("phase_1"),
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
                for r in revised:
                    r.pop("Index", None)
                revised = _reassign_ids(revised)
                revised = _apply_feedback_fix_p1(draft, revised, feedback_text)

                history = st.session_state.get("phase_1_history", [])
                history.append({
                    "version": len(history),
                    "source": "user_feedback",
                    "feedback": feedback_text,
                    "agent_message": agent_message,
                    "data": list(revised),
                })
                st.session_state["phase_1_history"] = history
                st.session_state["phase_1_draft"] = copy.deepcopy(revised)
                st.session_state["phase_1_feedback_message"] = agent_message
                st.session_state["phase_1_feedback_key"] = st.session_state.get("phase_1_feedback_key", 0) + 1
                save_on_action()
                st.rerun()
            except (ValueError, ConnectionError) as e:
                st.error(f"Failed to apply feedback: {e}")

    _render_history(st.session_state.get("phase_1_history", []))

    # ---- Approve ----
    st.markdown("---")
    if st.button("Approve & Save ✓", type="primary", key="p1_approve"):
        st.session_state["phase_1_approved"] = draft
        st.session_state["phase_1_complete"] = True

        # Persist only the approved risk list; feedback history and agent_message are not saved.
        out_path = get_session_output_dir() / "phase_1_approved.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, indent=2)

        save_on_action()
        swap_model("phase_1", "phase_2")
        st.rerun()

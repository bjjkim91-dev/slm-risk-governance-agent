"""Summary page: governance register view, AI verdict, and export."""

import json
import streamlit as st

from ui.session_manager import get_session_output_dir, get_download_prefix
from ui.exporters import build_excel, build_pdf
from ui.styles import phase_banner, metric_row, html_table


def _compute_coverage(p1: list, p2: list, p3: list):
    """Compute coverage from data: status per risk, counts, and overall verdict text.
    Returns (verdict_map, total_risks, n_covered, n_partial, n_gaps, overall_status, overall_verdict_text, risk_rows).
    verdict_map: risk_id -> '🔴 Gap' | '🟡 Partially Covered' | '🟢 Covered'
    """
    if not p1:
        return {}, 0, 0, 0, 0, "Not Ready", "No risks identified.", []

    p1_risk_ids = set(r.get("risk_id", "") for r in p1)
    p2_risk_ids = set(r.get("risk_id", "") for r in p2) if p2 else set()
    p2_control_ids = set(r.get("control_id", "") for r in p2) if p2 else set()
    p3_control_ids = set(r.get("control_id", "") for r in p3) if p3 else set()

    risks_without_control = p1_risk_ids - p2_risk_ids
    controls_with_process = p3_control_ids if p3 else set()
    controls_without_process = p2_control_ids - controls_with_process if p2 else set()

    # Per-risk status from data
    verdict_map = {}
    p2_cids_by_rid = {}
    if p2:
        for m in p2:
            rid = m.get("risk_id", "")
            cid = m.get("control_id", "")
            p2_cids_by_rid.setdefault(rid, set()).add(cid)

    risk_rows = []
    n_covered = n_partial = n_gaps = 0
    for r in p1:
        rid = r.get("risk_id", "")
        stmt = r.get("risk_statement", "")[:80]
        if rid in risks_without_control:
            status = "No control"
            reason = "No control assigned"
            n_gaps += 1
        else:
            cids = p2_cids_by_rid.get(rid, set())
            has_process = any(cid in controls_with_process for cid in cids)
            if has_process and cids <= controls_with_process:
                status = "Covered"
                reason = "Control(s) mapped to process"
                n_covered += 1
            else:
                status = "No process"
                reason = "Control has no process mapping"
                n_partial += 1
        verdict_map[rid] = {"Covered": "🟢 Covered", "No process": "🔴 No process", "No control": "🔴 No control"}[status]
        risk_rows.append({"risk_id": rid, "risk_statement": stmt, "status": status, "reason": reason})

    total_risks = len(p1)
    if n_gaps > 0:
        overall_status = "Not Ready"
        overall_verdict_text = (
            f"{total_risks} risk(s) identified. {total_risks - n_gaps} have control(s) assigned. "
            f"{n_gaps} risk(s) have no control — assign controls to close the gap."
        )
    elif n_partial > 0:
        overall_status = "Partially Ready"
        overall_verdict_text = (
            f"{total_risks} risk(s) identified with control(s) assigned. "
            f"{n_covered} fully mapped to processes, {n_partial} control(s) have no process mapping yet."
        )
    else:
        overall_status = "Ready"
        overall_verdict_text = (
            f"{total_risks} risk(s) identified with full coverage: all have controls and process mappings."
        )

    return verdict_map, total_risks, n_covered, n_partial, n_gaps, overall_status, overall_verdict_text, risk_rows


def _build_full_mapping_rows(p1: list, p2: list, p3: list, verdict_map: dict) -> list[dict]:
    """Build joined rows for Full Summary tab: risk, control, process, status (Converted / Not converted)."""
    if not p1:
        return []

    p1_by_rid = {r["risk_id"]: r for r in p1}
    p3_by_cid = {}
    for m in p3:
        cid = m.get("control_id", "")
        p3_by_cid.setdefault(cid, []).append(m)

    rows = []
    mapped_risk_ids = set()

    for m2 in p2:
        rid = m2.get("risk_id", "")
        cid = m2.get("control_id", "")
        mapped_risk_ids.add(rid)
        r1 = p1_by_rid.get(rid, {})
        p3_list = p3_by_cid.get(cid, [])
        coverage_label = verdict_map.get(rid, "🔴 No process")

        if not p3_list:
            rows.append({
                "Status": "🔴 No process" if not p3_list else coverage_label,
                "source_quote": r1.get("source_quote", ""),
                "risk_id": rid,
                "risk_statement": r1.get("risk_statement", ""),
                "control_id": cid,
                "control_description": m2.get("control_description", ""),
                "process_id": "",
                "process_name": "",
                "process_step": "",
                "why_process_assigned": "",
            })
        else:
            for m3 in p3_list:
                rows.append({
                    "Status": coverage_label,
                    "source_quote": r1.get("source_quote", ""),
                    "risk_id": rid,
                    "risk_statement": r1.get("risk_statement", ""),
                    "control_id": cid,
                    "control_description": m2.get("control_description", ""),
                    "process_id": m3.get("process_id", ""),
                    "process_name": m3.get("process_name", ""),
                    "process_step": m3.get("process_step", ""),
                    "why_process_assigned": m3.get("why_process_assigned", ""),
                })

    for r1 in p1:
        rid = r1.get("risk_id", "")
        if rid not in mapped_risk_ids:
            rows.append({
                "Status": verdict_map.get(rid, "🔴 Gap"),
                "source_quote": r1.get("source_quote", ""),
                "risk_id": rid,
                "risk_statement": r1.get("risk_statement", ""),
                "control_id": "",
                "control_description": "",
                "process_id": "",
                "process_name": "",
                "process_step": "",
                "why_process_assigned": "",
            })

    return rows


def render():
    st.markdown(
        phase_banner(
            "Summary & Verdict",
            "Review the full governance register and get an AI assessment against the COSO framework.",
            "📊",
        ),
        unsafe_allow_html=True,
    )

    p1 = st.session_state.get("phase_1_approved", [])
    p2 = st.session_state.get("phase_2_approved", [])
    p3 = st.session_state.get("phase_3_approved", [])

    has_any = bool(p1 or p2 or p3)

    if not has_any:
        st.info("No completed phases yet. Start by uploading documents and running Phase 1.")
        return

    # ---- Overall metrics ----
    p1_risk_ids = set(r.get("risk_id", "") for r in p1) if p1 else set()

    p2_risk_ids = set(r.get("risk_id", "") for r in p2) if p2 else set()
    p2_control_ids = set(r.get("control_id", "") for r in p2) if p2 else set()

    p3_control_ids = set(r.get("control_id", "") for r in p3) if p3 else set()
    p3_process_names = set(r.get("process_name", "") for r in p3) if p3 else set()

    risks_without_control = p1_risk_ids - p2_risk_ids if p2 else p1_risk_ids
    controls_without_process = p2_control_ids - p3_control_ids if p3 else p2_control_ids

    metrics = [(len(p1), "Risks Identified")]
    if p2:
        metrics.append((len(p2_control_ids), "Controls Mapped"))
        metrics.append((len(p2), "Risk-Control Links"))
    if p3:
        metrics.append((len(p3_process_names), "Processes"))
        metrics.append((len(p3), "Total Mappings"))

    st.markdown(metric_row(metrics), unsafe_allow_html=True)

    # Coverage gap indicators
    if p2 and risks_without_control:
        st.warning(f"⚠️ **{len(risks_without_control)}** risk(s) have no control mapped: {', '.join(sorted(risks_without_control))}")
        st.caption("These risks are in your approved Phase 1 list but have no control mapping in Phase 2 — not deleted. Assign controls in Phase 2 to close the gap.")
    if p3 and controls_without_process:
        st.warning(f"⚠️ **{len(controls_without_process)}** control(s) have no process mapped: {', '.join(sorted(controls_without_process))}")
        st.caption("These controls are mapped in Phase 2 but have no process in Phase 3 — not deleted. Map to processes in Phase 3 to close the gap.")
    if p2 and not risks_without_control and p3 and not controls_without_process:
        st.success("✅ All risks have controls and all controls have processes mapped.")

    st.markdown("")

    # Verdict and coverage from actual data (so verdict text and Full tab match)
    verdict_map, total_risks, n_covered, n_partial, n_gaps, overall_status, overall_verdict_text, computed_risk_rows = _compute_coverage(p1, p2, p3)

    # ---- Tabs: Full Summary first (default), then Risk | Control | Process ----
    available_tabs = ["Full Summary"]
    if p1:
        available_tabs.append("Risk")
    if p2:
        available_tabs.append("Control")
    if p3:
        available_tabs.append("Process")

    if available_tabs:
        try:
            tabs = st.tabs(available_tabs, default="Full Summary")
        except TypeError:
            tabs = st.tabs(available_tabs)

        _RISK_TAB_COLS = [
            ("risk_id", "Risk ID", "col-id"),
            ("risk_statement", "Risk", "col-xl"),
            ("severity", "Severity", "col-sm"),
            ("risk_category", "Category", "col-md"),
            ("why_identified", "Rationale", "col-xl"),
        ]
        _CTRL_TAB_COLS = [
            ("risk_id", "Risk ID", "col-id"),
            ("risk_statement", "Risk", "col-lg"),
            ("control_id", "Control ID", "col-id"),
            ("control_description", "Control Description", "col-xl"),
            ("control_type", "Type", "col-sm"),
            ("why_control_assigned", "Rationale", "col-xl"),
        ]
        _PROC_TAB_COLS = [
            ("control_id", "Control ID", "col-id"),
            ("control_description", "Control Description", "col-lg"),
            ("process_id", "Process ID", "col-id"),
            ("process_name", "Process Step", "col-lg"),
            ("process_step", "Process Detail", "col-lg"),
            ("why_process_assigned", "Rationale", "col-xl"),
        ]
        _FULL_TAB_COLS = [
            ("Status", "Status", "col-sm"),
            ("source_quote", "Quote", "col-xl"),
            ("risk_id", "Risk ID", "col-id"),
            ("risk_statement", "Risk", "col-lg"),
            ("control_id", "Control ID", "col-id"),
            ("control_description", "Control Description", "col-lg"),
            ("process_id", "Process ID", "col-id"),
            ("process_name", "Process Step", "col-md"),
            ("process_step", "Process Detail", "col-md"),
        ]

        # Tab 0 = Full Summary (default)
        with tabs[0]:
            full_rows = _build_full_mapping_rows(p1, p2, p3, verdict_map)
            if full_rows:
                cols = [(k, l, s) for k, l, s in _FULL_TAB_COLS if any(k in r for r in full_rows)]
                st.markdown(html_table(full_rows, cols), unsafe_allow_html=True)
                covered = sum(1 for r in full_rows if "🟢 Covered" in r.get("Status", ""))
                no_control_count = sum(1 for r in full_rows if "No control" in r.get("Status", ""))
                no_process_count = sum(1 for r in full_rows if "No process" in r.get("Status", ""))
                st.markdown(
                    metric_row([
                        (covered, "🟢 Covered"),
                        (no_process_count, "🔴 No process"),
                        (no_control_count, "🔴 No control"),
                    ]),
                    unsafe_allow_html=True,
                )
            else:
                st.info("Complete Phase 1 to see the full summary. Run Phase 2 and 3 for control and process columns.")

        tab_idx = 1
        if p1:
            with tabs[tab_idx]:
                cols = [(k, l, s) for k, l, s in _RISK_TAB_COLS if any(k in r for r in p1)]
                st.markdown(html_table(p1, cols), unsafe_allow_html=True)
            tab_idx += 1

        if p2:
            with tabs[tab_idx]:
                cols = [(k, l, s) for k, l, s in _CTRL_TAB_COLS if any(k in r for r in p2)]
                st.markdown(html_table(p2, cols), unsafe_allow_html=True)
            tab_idx += 1

        if p3:
            with tabs[tab_idx]:
                cols = [(k, l, s) for k, l, s in _PROC_TAB_COLS if any(k in r for r in p3)]
                st.markdown(html_table(p3, cols), unsafe_allow_html=True)

    # ---- Governance Verdict (computed from data; no button required) ----
    st.markdown("---")
    st.markdown("### Governance Verdict")

    if not p1:
        st.warning("Complete at least Phase 1 to see the verdict.")
    else:
        # Verdict is always computed from approved data (overall status + verdict text). No recommendations generated — gaps are evident from the table.
        ai_recs = (st.session_state.get("verdict") or {}).get("recommendations", [])
        merged = {
            "overall_status": overall_status,
            "overall_verdict": overall_verdict_text,
            "risks": computed_risk_rows,
            "recommendations": ai_recs,
        }
        _render_verdict(merged)

    # ---- Export ----
    st.markdown("---")
    st.markdown("### Export Full Report")

    prefix = get_download_prefix()
    session_names = st.session_state.get("session_names", {})
    active_id = st.session_state.get("active_session_id", "")
    session_label = session_names.get(active_id, prefix)
    ai_recs = (st.session_state.get("verdict") or {}).get("recommendations", [])
    export_verdict = {
        "overall_status": overall_status,
        "overall_verdict": overall_verdict_text,
        "risks": computed_risk_rows,
        "recommendations": ai_recs,
    } if p1 else None

    col1, col2 = st.columns(2)
    with col1:
        # Export uses only approved data and computed verdict; no feedback history or agent_message.
        xlsx_bytes = build_excel(
            p1=p1 or None, p2=p2 or None, p3=p3 or None,
            verdict=export_verdict, session_name=session_label,
        )
        st.download_button(
            "📥 Download Excel",
            data=xlsx_bytes,
            file_name=f"{prefix}_governance_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.caption("One tab per phase + verdict summary")
    with col2:
        # PDF uses same approved data + verdict; no feedback/agent_message.
        pdf_bytes = build_pdf(
            p1=p1 or None, p2=p2 or None, p3=p3 or None,
            verdict=export_verdict, session_name=session_label,
        )
        st.download_button(
            "📥 Download PDF",
            data=pdf_bytes,
            file_name=f"{prefix}_governance_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        st.caption("Full report: P1 → P2 → P3 → Verdict")


def _render_verdict(verdict: dict):
    """Display the AI-generated verdict with styled cards."""
    overall_status = verdict.get("overall_status", "Unknown")
    overall_verdict = verdict.get("overall_verdict", "")
    risks = verdict.get("risks", [])
    recommendations = verdict.get("recommendations", [])

    # Status card
    status_class = {
        "Ready": "verdict-ready",
        "Partially Ready": "verdict-partial",
        "Not Ready": "verdict-not-ready",
    }.get(overall_status, "")

    status_icon = {
        "Ready": "🟢",
        "Partially Ready": "🟡",
        "Not Ready": "🔴",
    }.get(overall_status, "⚪")

    st.markdown(
        f'<div class="card {status_class}">'
        f'<div class="card-header">{status_icon} Overall Status: {overall_status}</div>'
        f'<p style="margin:0; opacity:0.8;">{overall_verdict}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if risks:
        st.markdown("#### Per-Risk Assessment")

        status_icons = {
            "Covered": "🟢",
            "No control": "🔴",
            "No process": "🔴",
        }

        risk_rows = []
        for r in risks:
            status = r.get("status", "Unknown")
            icon = status_icons.get(status, "⚪")
            risk_rows.append({
                "Status": f"{icon} {status}",
                "risk_id": r.get("risk_id", ""),
                "risk_statement": r.get("risk_statement", ""),
                "reason": r.get("reason", ""),
            })

        verdict_cols = [
            ("Status", "Status", "col-sm"),
            ("risk_id", "Risk ID", "col-id"),
            ("risk_statement", "Risk", "col-xl"),
            ("reason", "Reason", "col-lg"),
        ]
        st.markdown(html_table(risk_rows, verdict_cols), unsafe_allow_html=True)

        covered = sum(1 for r in risks if r.get("status") == "Covered")
        no_process = sum(1 for r in risks if r.get("status") == "No process")
        no_control = sum(1 for r in risks if r.get("status") == "No control")

        st.markdown(
            metric_row([
                (covered, "Covered"),
                (no_process, "No process"),
                (no_control, "No control"),
            ]),
            unsafe_allow_html=True,
        )

    if recommendations:
        st.markdown("#### Recommendations")
        for i, rec in enumerate(recommendations, 1):
            st.markdown(f"**{i}.** {rec}")

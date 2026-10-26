"""History page: browse and download outputs from previous sessions saved to disk."""

import json
from pathlib import Path
from datetime import datetime

import streamlit as st

from config import OUTPUTS_DIR
from ui.styles import phase_banner, metric_row, html_table
from ui.exporters import build_excel, build_pdf


def _scan_sessions() -> list[dict]:
    """Scan OUTPUTS_DIR (data/outputs/<session_id>/) for session folders with output files."""
    if not OUTPUTS_DIR.is_dir():
        return []

    sessions = []
    for folder in sorted(OUTPUTS_DIR.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        meta_path = folder / "meta.json"
        if not meta_path.exists():
            output_files = [f.name for f in folder.iterdir() if f.suffix == ".json"]
            if not output_files:
                continue
            meta = {
                "session_id": folder.name,
                "session_name": folder.name,
                "updated_at": datetime.fromtimestamp(folder.stat().st_mtime).isoformat(),
                "phases_complete": {"phase_1": False, "phase_2": False, "phase_3": False},
                "counts": {},
                "has_verdict": "verdict.json" in output_files,
            }
        else:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)

        meta["_folder"] = folder
        sessions.append(meta)

    sessions.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
    return sessions


def _load_json(folder: Path, filename: str):
    """Load a JSON file from a session folder, return None if missing."""
    path = folder / filename
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _format_timestamp(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %d, %Y  %H:%M")
    except (ValueError, TypeError):
        return iso


def _safe_prefix(name: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower() or "session"


def render():
    st.markdown(
        phase_banner(
            "History",
            "Browse and download reports from previous sessions.",
            "🗂️",
        ),
        unsafe_allow_html=True,
    )

    sessions = _scan_sessions()

    if not sessions:
        st.info(
            "No saved sessions found. Outputs are saved to disk when you click "
            '"Approve & Save" in each phase.'
        )
        return

    st.markdown(f"**{len(sessions)}** saved session(s) found")
    st.markdown("")

    for meta in sessions:
        session_name = meta.get("session_name", meta["session_id"])
        updated = _format_timestamp(meta.get("updated_at", ""))
        folder: Path = meta["_folder"]
        phases = meta.get("phases_complete", {})
        counts = meta.get("counts", {})
        has_verdict = meta.get("has_verdict", False)

        p1_icon = "✅" if phases.get("phase_1") else "⬜"
        p2_icon = "✅" if phases.get("phase_2") else "⬜"
        p3_icon = "✅" if phases.get("phase_3") else "⬜"
        verdict_icon = "✅" if has_verdict else "⬜"

        with st.expander(f"**{session_name}**  ·  {updated}  ·  {p1_icon}P1 {p2_icon}P2 {p3_icon}P3 {verdict_icon}V"):
            # Counts
            count_items = []
            if counts.get("risks"):
                count_items.append((counts["risks"], "Risks"))
            if counts.get("control_mappings"):
                count_items.append((counts["control_mappings"], "Control Mappings"))
            if counts.get("process_mappings"):
                count_items.append((counts["process_mappings"], "Process Mappings"))
            if count_items:
                st.markdown(metric_row(count_items), unsafe_allow_html=True)
                st.markdown("")

            # Load data for export
            p1 = _load_json(folder, "phase_1_approved.json")
            p2 = _load_json(folder, "phase_2_approved.json")
            p3 = _load_json(folder, "phase_3_approved.json")
            verdict = _load_json(folder, "verdict.json")

            has_data = any([p1, p2, p3, verdict])

            if has_data:
                prefix = _safe_prefix(session_name)

                # Preview tabs
                preview_tabs = []
                if p1:
                    preview_tabs.append("Risk Register")
                if p2:
                    preview_tabs.append("Risk-Control")
                if p3:
                    preview_tabs.append("Governance Map")
                if verdict:
                    preview_tabs.append("Verdict")

                if preview_tabs:
                    tabs = st.tabs(preview_tabs)
                    tab_i = 0
                    if p1:
                        with tabs[tab_i]:
                            _cols = [("risk_id","Risk ID","col-id"),("risk_statement","Risk","col-xl"),("severity","Severity","col-sm")]
                            st.markdown(html_table(p1[:10], _cols), unsafe_allow_html=True)
                            if len(p1) > 10:
                                st.caption(f"Showing 10 of {len(p1)} rows")
                        tab_i += 1
                    if p2:
                        with tabs[tab_i]:
                            _cols = [("risk_id","Risk ID","col-id"),("control_id","Control ID","col-id"),("control_description","Control Description","col-xl"),("control_type","Type","col-sm")]
                            st.markdown(html_table(p2[:10], _cols), unsafe_allow_html=True)
                            if len(p2) > 10:
                                st.caption(f"Showing 10 of {len(p2)} rows")
                        tab_i += 1
                    if p3:
                        with tabs[tab_i]:
                            _cols = [("control_id","Control ID","col-id"),("control_description","Control Description","col-lg"),("process_name","Process Step","col-lg"),("process_step","Process Detail","col-lg")]
                            st.markdown(html_table(p3[:10], _cols), unsafe_allow_html=True)
                            if len(p3) > 10:
                                st.caption(f"Showing 10 of {len(p3)} rows")
                        tab_i += 1
                    if verdict:
                        with tabs[tab_i]:
                            st.markdown(f"**Status:** {verdict.get('overall_status', 'N/A')}")
                            st.markdown(f"_{verdict.get('overall_verdict', '')}_")

                st.markdown("")

                # Download buttons: Excel + PDF only
                col1, col2 = st.columns(2)
                with col1:
                    xlsx = build_excel(p1=p1, p2=p2, p3=p3, verdict=verdict, session_name=session_name)
                    st.download_button(
                        "📥 Download Excel",
                        data=xlsx,
                        file_name=f"{prefix}_governance_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"hist_{meta['session_id']}_xlsx",
                        use_container_width=True,
                    )
                with col2:
                    pdf = build_pdf(p1=p1, p2=p2, p3=p3, verdict=verdict, session_name=session_name)
                    st.download_button(
                        "📥 Download PDF",
                        data=pdf,
                        file_name=f"{prefix}_governance_report.pdf",
                        mime="application/pdf",
                        key=f"hist_{meta['session_id']}_pdf",
                        use_container_width=True,
                    )
            else:
                st.caption("No output files found in this session.")

            st.markdown("")
            if st.button(
                "🗑️ Delete this session's outputs",
                key=f"del_{meta['session_id']}",
                type="secondary",
            ):
                import shutil
                shutil.rmtree(folder, ignore_errors=True)
                st.success(f"Deleted outputs for {session_name}")
                st.rerun()

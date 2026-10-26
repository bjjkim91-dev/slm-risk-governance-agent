"""Upload page: separate file uploaders for regulatory, control, and process docs."""

import hashlib
import streamlit as st
from ingestion import extract_text, chunk_text
from config import (
    SUPPORTED_FILE_TYPES,
    CHUNK_SIZE_CHARS,
    CHUNK_OVERLAP_CHARS,
    CONTROL_CHUNK_SIZE_CHARS,
    CONTROL_CHUNK_OVERLAP_CHARS,
)
from ui.styles import phase_banner, metric_row
from ui.session_manager import get_session_uploads_dir


def _fingerprint(files: list[dict]) -> str:
    """Stable hash from sorted filenames+sizes to detect document changes."""
    sig = "|".join(sorted(f"{f['name']}:{f['size']}" for f in files))
    return hashlib.md5(sig.encode()).hexdigest()[:12]


PHASE_RESET_MAP = {
    "regulatory_files": {
        "fingerprint_key": "regulatory_fp",
        "phases_to_reset": [
            "phase_1_draft", "phase_1_approved", "phase_1_complete", "phase_1_history",
            "phase_2_draft", "phase_2_approved", "phase_2_complete", "phase_2_history",
            "phase_3_draft", "phase_3_approved", "phase_3_complete", "phase_3_history",
            "verdict",
        ],
        "label": "Regulatory",
    },
    "control_files": {
        "fingerprint_key": "control_fp",
        "phases_to_reset": [
            "phase_2_draft", "phase_2_approved", "phase_2_complete", "phase_2_history",
            "phase_3_draft", "phase_3_approved", "phase_3_complete", "phase_3_history",
            "verdict",
        ],
        "label": "Control",
    },
    "process_files": {
        "fingerprint_key": "process_fp",
        "phases_to_reset": [
            "phase_3_draft", "phase_3_approved", "phase_3_complete", "phase_3_history",
            "verdict",
        ],
        "label": "Process",
    },
}


def _reset_downstream(files_key: str, new_fp: str):
    """Clear downstream phase data when source documents change."""
    cfg = PHASE_RESET_MAP[files_key]
    old_fp = st.session_state.get(cfg["fingerprint_key"])

    if old_fp is not None and old_fp != new_fp:
        reset_keys = cfg["phases_to_reset"]
        had_data = any(st.session_state.get(k) for k in reset_keys)

        for k in reset_keys:
            if k.endswith("_complete"):
                st.session_state[k] = False
            elif k == "verdict":
                st.session_state[k] = None
            else:
                st.session_state[k] = []

        if had_data:
            st.warning(
                f"⚠️ {cfg['label']} documents changed — downstream phase results have been reset. "
                f"You'll need to re-run affected phases."
            )

    st.session_state[cfg["fingerprint_key"]] = new_fp


def _process_uploads(uploaded_files: list, files_key: str) -> tuple[list, list]:
    """Extract text and chunk each uploaded file. Saves copies to session upload folder. Returns (file_records, chunks)."""
    file_records = []
    all_chunks = []
    upload_dir = get_session_uploads_dir()

    # Use larger chunks for control docs so Phase 2 sees more inventory per LLM call.
    if files_key == "control_files":
        chunk_size, overlap = CONTROL_CHUNK_SIZE_CHARS, CONTROL_CHUNK_OVERLAP_CHARS
    else:
        chunk_size, overlap = CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS

    for uf in uploaded_files:
        file_bytes = uf.read()
        uf.seek(0)
        file_records.append({"name": uf.name, "size": len(file_bytes)})

        if upload_dir:
            try:
                (upload_dir / uf.name).write_bytes(file_bytes)
            except OSError:
                pass

        try:
            text = extract_text(file_bytes, uf.name)
            chunks = chunk_text(text, source_name=uf.name, chunk_size=chunk_size, overlap=overlap)
            all_chunks.extend(chunks)
        except (ValueError, ImportError) as e:
            st.error(f"Error processing {uf.name}: {e}")

    new_fp = _fingerprint(file_records)
    _reset_downstream(files_key, new_fp)

    return file_records, all_chunks


def _file_chips(files: list[dict]) -> str:
    """Render file names as styled chips."""
    if not files:
        return '<span style="opacity:0.5; font-size:0.85rem;">No files uploaded</span>'
    chips = ""
    for f in files:
        size_kb = f.get("size", 0) / 1024
        chips += f'<span class="file-chip">📄 {f["name"]} ({size_kb:.0f} KB)</span>'
    return chips


def _upload_section(
    num: int,
    title: str,
    description: str,
    icon: str,
    uploader_key: str,
    files_key: str,
    chunks_key: str,
):
    """Render a single upload section with card styling."""
    ext_label = ", ".join(SUPPORTED_FILE_TYPES)

    st.markdown(
        f'<div class="card">'
        f'<div class="card-header">{icon} {num}. {title}</div>'
        f'<p style="font-size:0.85rem; opacity:0.7; margin:0 0 0.8rem 0;">'
        f'{description} &nbsp;·&nbsp; Accepted: {ext_label}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        f"Upload {title.lower()}",
        type=[ext.lstrip(".") for ext in SUPPORTED_FILE_TYPES],
        accept_multiple_files=True,
        key=uploader_key,
        label_visibility="collapsed",
    )

    if uploaded:
        records, chunks = _process_uploads(uploaded, files_key)
        st.session_state[files_key] = records
        st.session_state[chunks_key] = chunks

        st.markdown(_file_chips(records), unsafe_allow_html=True)
        st.success(f"{len(records)} file(s) loaded  ·  {len(chunks)} chunk(s) extracted")

        with st.expander("Preview chunks"):
            for c in chunks[:5]:
                st.text(f"[{c['source_name']} | chunk {c['chunk_index']}]")
                st.text(c["text"][:300] + ("..." if len(c["text"]) > 300 else ""))
                st.markdown("---")
    else:
        existing = st.session_state.get(files_key, [])
        if existing:
            st.markdown(_file_chips(existing), unsafe_allow_html=True)


def render():
    st.markdown(
        phase_banner(
            "Upload Documents",
            "Upload regulatory, control, and process documents. All file types can be uploaded upfront.",
            "📁",
        ),
        unsafe_allow_html=True,
    )

    _upload_section(
        num=1,
        title="Regulatory / Policy Documents",
        description="Used in Phase 1 to extract compliance risks.",
        icon="📜",
        uploader_key="reg_uploader",
        files_key="regulatory_files",
        chunks_key="regulatory_chunks",
    )

    _upload_section(
        num=2,
        title="Control Documents",
        description="Used in Phase 2 to map risks to controls.",
        icon="🔒",
        uploader_key="ctrl_uploader",
        files_key="control_files",
        chunks_key="control_chunks",
    )

    _upload_section(
        num=3,
        title="Process Documents",
        description="Used in Phase 3 to map controls to business processes.",
        icon="⚙️",
        uploader_key="proc_uploader",
        files_key="process_files",
        chunks_key="process_chunks",
    )

    # Summary metrics
    st.markdown("---")
    reg = len(st.session_state.get("regulatory_files", []))
    ctrl = len(st.session_state.get("control_files", []))
    proc = len(st.session_state.get("process_files", []))
    total_chunks = (
        len(st.session_state.get("regulatory_chunks", []))
        + len(st.session_state.get("control_chunks", []))
        + len(st.session_state.get("process_chunks", []))
    )

    st.markdown(
        metric_row([
            (reg, "Regulatory Files"),
            (ctrl, "Control Files"),
            (proc, "Process Files"),
            (total_chunks, "Total Chunks"),
        ]),
        unsafe_allow_html=True,
    )

    if reg > 0:
        st.markdown("")
        if st.button("Continue to Phase 1 →", type="primary"):
            st.session_state["current_page"] = "Phase 1 – Risks"
            st.rerun()

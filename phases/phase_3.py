"""Phase 3 runner: Control × Process documents → Governance Map."""

from __future__ import annotations

from schemas import make_row_id
from prompts.phase_3 import build_phase_3_prompt
from llm_client import generate_json, get_model
from config import CONTROL_PROCESS_MAPPING_PREFIX


def run_phase_3(
    approved_risk_controls: list[dict],
    process_chunks: list[dict],
) -> list[dict]:
    """Map approved controls to processes found in process documents.

    Args:
        approved_risk_controls: list of approved RiskControlEntry dicts from Phase 2.
        process_chunks: list of chunk dicts from process document ingestion.

    Returns:
        list of GovernanceEntry-compatible dicts.
    """
    all_mappings: list[dict] = []

    # Build lookups from approved Phase 2 data
    valid_control_ids = {rc["control_id"] for rc in approved_risk_controls}
    rc_map = {rc["control_id"]: rc.get("risk_control_mapping_id", "") for rc in approved_risk_controls}
    ctrl_info_map = {rc["control_id"]: rc for rc in approved_risk_controls}

    slim_controls = [
        {
            "control_id": rc["control_id"],
            "risk_control_mapping_id": rc.get("risk_control_mapping_id", ""),
            "control_description": rc.get("control_description", ""),
        }
        for rc in approved_risk_controls
    ]

    for chunk in process_chunks:
        prompt = build_phase_3_prompt(slim_controls, chunk["text"])
        try:
            raw_results = generate_json(prompt, model=get_model("phase_3"))
        except (ValueError, ConnectionError) as e:
            all_mappings.append({
                "control_process_mapping_id": "",
                "risk_control_mapping_id": "",
                "control_id": "?",
                "control_description": f"[ERROR on process chunk {chunk.get('chunk_index', '?')}]",
                "process_id": "",
                "process_name": str(e),
                "process_step": "",
                "why_process_assigned": "LLM mapping failed for this chunk",
                "user_status": "Proposed",
                "user_notes": None,
            })
            continue

        if isinstance(raw_results, dict):
            raw_results = [raw_results]

        for item in raw_results:
            cid = item.get("control_id", "")
            # Reject mappings with control IDs not in approved Phase 2 output
            if cid not in valid_control_ids:
                continue
            rc_info = ctrl_info_map.get(cid, {})

            process_name = (item.get("process_name") or "").strip()
            if not process_name:
                continue

            entry = {
                "control_process_mapping_id": "",
                "risk_control_mapping_id": rc_map.get(cid, "") or "",
                "control_id": cid,
                "control_description": (rc_info.get("control_description") or ""),
                "process_id": (item.get("process_id") or ""),
                "process_name": process_name,
                "process_step": (item.get("process_step") or ""),
                "why_process_assigned": (item.get("why_process_assigned") or ""),
                "user_status": "Proposed",
                "user_notes": None,
            }
            all_mappings.append(entry)

    for i, m in enumerate(all_mappings, start=1):
        m["control_process_mapping_id"] = make_row_id(CONTROL_PROCESS_MAPPING_PREFIX, i)

    # Remove exact duplicates (same control + process name)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for m in all_mappings:
        key = (m["control_id"], m["process_name"], m["process_step"])
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique

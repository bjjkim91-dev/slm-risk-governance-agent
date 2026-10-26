"""Phase 2 runner: Risk × Control documents → Risk-Control mapping."""

from __future__ import annotations

from schemas import make_row_id
from prompts.phase_2 import build_phase_2_prompt
from llm_client import generate_json, get_model
from config import RISK_CONTROL_MAPPING_PREFIX

_CONTROL_TYPES = {"preventive", "detective", "corrective"}
_EXECUTION_TYPES = {"manual", "automated", "hybrid"}


def _normalise_choice(raw: str, allowed: set[str], default: str) -> str:
    low = raw.strip().lower()
    if low in allowed:
        return low.capitalize()
    return default


def run_phase_2(
    approved_risks: list[dict],
    control_chunks: list[dict],
) -> list[dict]:
    """Map approved risks to controls found in control documents.

    Args:
        approved_risks: list of approved RiskEntry dicts from Phase 1.
        control_chunks: list of chunk dicts from control document ingestion.

    Returns:
        list of RiskControlEntry-compatible dicts.
    """
    all_mappings: list[dict] = []

    slim_risks = [
        {
            "risk_id": r["risk_id"],
            "input_risk_mapping_id": r.get("input_risk_mapping_id", ""),
            "risk_statement": r["risk_statement"],
            "severity": r["severity"],
        }
        for r in approved_risks
    ]

    # Build lookups from approved Phase 1 data
    valid_risk_ids = {r["risk_id"] for r in approved_risks}
    risk_row_map = {r["risk_id"]: r.get("input_risk_mapping_id", "") for r in approved_risks}
    risk_info_map = {r["risk_id"]: r for r in approved_risks}

    for chunk in control_chunks:
        prompt = build_phase_2_prompt(slim_risks, chunk["text"])
        try:
            raw_results = generate_json(prompt, model=get_model("phase_2"))
        except (ValueError, ConnectionError) as e:
            all_mappings.append({
                "risk_control_mapping_id": "",
                "input_risk_mapping_id": "",
                "risk_id": "?",
                "risk_statement": f"[ERROR on control chunk {chunk.get('chunk_index', '?')}]",
                "control_id": "",
                "control_description": str(e),
                "why_control_assigned": "LLM mapping failed for this chunk",
                "control_type": "",
                "execution_type": "",
                "user_status": "Proposed",
                "user_notes": None,
            })
            continue

        if isinstance(raw_results, dict):
            raw_results = [raw_results]

        for item in raw_results:
            rid = item.get("risk_id", "")
            # Reject mappings with risk IDs not in approved Phase 1 output
            if rid not in valid_risk_ids:
                continue
            risk_info = risk_info_map.get(rid, {})

            control_desc = item.get("control_description", "").strip()
            if not control_desc:
                continue

            mapping = {
                "risk_control_mapping_id": "",
                "input_risk_mapping_id": risk_row_map.get(rid, ""),
                "risk_id": rid,
                "risk_statement": risk_info.get("risk_statement", ""),
                "control_id": item.get("control_id", ""),
                "control_description": control_desc,
                "why_control_assigned": item.get("why_control_assigned", ""),
                "control_type": _normalise_choice(item.get("control_type", ""), _CONTROL_TYPES, "Preventive"),
                "execution_type": _normalise_choice(item.get("execution_type", ""), _EXECUTION_TYPES, "Manual"),
                "user_status": "Proposed",
                "user_notes": None,
            }
            all_mappings.append(mapping)

    # Assign sequential row IDs
    for i, m in enumerate(all_mappings, start=1):
        m["risk_control_mapping_id"] = make_row_id(RISK_CONTROL_MAPPING_PREFIX, i)

    # Remove exact duplicates (same risk_id + same control_description)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for m in all_mappings:
        key = (m["risk_id"], m["control_description"])
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique

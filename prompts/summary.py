"""Summary verdict prompt builder: assess governance register for coverage."""

from __future__ import annotations

import json


SUMMARY_SYSTEM = """You are a risk governance assessment assistant.
You will receive a governance register with PRE-COMPUTED coverage metrics.
Your job is to write actionable recommendations for any gaps — NOT to re-count or re-derive the metrics.
Output valid JSON only.

## YOUR TASK
Pre-computed coverage data + full summary table → actionable recommendations.

## COVERAGE STATUS VALUES
- Covered: risk has control AND control has process.
- No process: risk has control but control has no process mapping.
- No control: risk has no control assigned.

## RECOMMENDATION RULES
- Each recommendation MUST reference a specific risk_id, control_id, or process_id.
- Recommendations must be specific and actionable, not generic compliance advice.
- Do not invent counts, statuses, or coverage numbers.
- Do not re-derive overall_status or overall_verdict — those are already computed.
- Do not claim control effectiveness, audit readiness, or full compliance.
- If there are no gaps (n_no_control = 0 and n_no_process = 0), return an empty array.

## OUTPUT COLUMNS
Return a single JSON object with ONLY this field:
- recommendations: array of strings — specific actionable next steps for gaps
"""


def _build_full_summary_rows(
    p1_risks: list[dict],
    p2_mappings: list[dict],
    p3_mappings: list[dict],
) -> list[dict]:
    """Build the same full-summary rows shown in the Full Summary tab (risk, control, process, status).
    Used as the primary input for the verdict so recommendations match the tab."""
    if not p1_risks:
        return []

    p1_by_rid = {r["risk_id"]: r for r in p1_risks}
    p3_by_cid = {}
    for m in p3_mappings:
        cid = m.get("control_id", "")
        p3_by_cid.setdefault(cid, []).append(m)

    rows = []
    mapped_risk_ids = set()

    for m2 in p2_mappings:
        rid = m2.get("risk_id", "")
        cid = m2.get("control_id", "")
        mapped_risk_ids.add(rid)
        r1 = p1_by_rid.get(rid, {})
        p3_list = p3_by_cid.get(cid, [])

        if not p3_list:
            rows.append({
                "status": "not_converted",
                "reason": "control has no process mapping",
                "risk_id": rid,
                "risk_statement": r1.get("risk_statement", ""),
                "control_id": cid,
                "control_description": m2.get("control_description", ""),
                "process_id": "",
                "process_name": "",
                "process_step": "",
            })
        else:
            for m3 in p3_list:
                rows.append({
                    "status": "converted",
                    "reason": "full chain",
                    "risk_id": rid,
                    "risk_statement": r1.get("risk_statement", ""),
                    "control_id": cid,
                    "control_description": m2.get("control_description", ""),
                    "process_id": m3.get("process_id", ""),
                    "process_name": m3.get("process_name", ""),
                    "process_step": m3.get("process_step", ""),
                })

    for r1 in p1_risks:
        rid = r1.get("risk_id", "")
        if rid not in mapped_risk_ids:
            rows.append({
                "status": "not_converted",
                "reason": "risk has no control",
                "risk_id": rid,
                "risk_statement": r1.get("risk_statement", ""),
                "control_id": "",
                "control_description": "",
                "process_id": "",
                "process_name": "",
                "process_step": "",
            })

    return rows


def _precompute_coverage(p1_risks, p2_mappings, p3_mappings):
    """Return computed coverage dict with per-risk status and aggregate counts."""
    p1_risk_ids = set(r.get("risk_id", "") for r in p1_risks)
    p2_risk_ids = set(r.get("risk_id", "") for r in p2_mappings)
    p2_control_ids = set(r.get("control_id", "") for r in p2_mappings)
    p3_control_ids = set(r.get("control_id", "") for r in p3_mappings)

    risks_without_control = p1_risk_ids - p2_risk_ids
    controls_with_process = p3_control_ids
    controls_without_process = p2_control_ids - controls_with_process

    p2_cids_by_rid = {}
    for m in p2_mappings:
        p2_cids_by_rid.setdefault(m.get("risk_id", ""), set()).add(m.get("control_id", ""))

    risk_statuses = []
    for r in p1_risks:
        rid = r.get("risk_id", "")
        stmt = r.get("risk_statement", "")[:80]
        if rid in risks_without_control:
            risk_statuses.append({"risk_id": rid, "risk_statement": stmt, "status": "No control", "reason": "No control assigned"})
        else:
            cids = p2_cids_by_rid.get(rid, set())
            if cids and cids <= controls_with_process:
                risk_statuses.append({"risk_id": rid, "risk_statement": stmt, "status": "Covered", "reason": "Control(s) mapped to process"})
            else:
                risk_statuses.append({"risk_id": rid, "risk_statement": stmt, "status": "No process", "reason": "Control has no process mapping"})

    n_covered = sum(1 for r in risk_statuses if r["status"] == "Covered")
    n_no_process = sum(1 for r in risk_statuses if r["status"] == "No process")
    n_no_control = sum(1 for r in risk_statuses if r["status"] == "No control")

    return {
        "total_risks": len(p1_risks),
        "total_controls_mapped": len(p2_control_ids),
        "risks_with_no_control": sorted(risks_without_control),
        "controls_without_process": sorted(controls_without_process),
        "n_covered": n_covered,
        "n_no_process": n_no_process,
        "n_no_control": n_no_control,
        "risk_statuses": risk_statuses,
    }


def build_summary_prompt(
    p1_risks: list[dict],
    p2_mappings: list[dict],
    p3_mappings: list[dict],
) -> str:
    """Assemble the summary verdict prompt. Coverage counts are pre-computed as facts."""
    full_summary = _build_full_summary_rows(p1_risks, p2_mappings, p3_mappings)
    full_summary_json = json.dumps(full_summary, indent=2)

    coverage = _precompute_coverage(p1_risks, p2_mappings, p3_mappings)
    coverage_json = json.dumps(coverage, indent=2)

    return f"""{SUMMARY_SYSTEM}

--- PRE-COMPUTED COVERAGE (these are FACTS — do NOT re-derive or change them) ---
{coverage_json}

--- FULL SUMMARY TABLE ---
{full_summary_json}

--- INSTRUCTION ---
Write actionable recommendations for any gaps listed above.
Return ONLY a JSON object: {{"recommendations": [...]}}
If there are no gaps, return {{"recommendations": []}}.
No other text."""

"""Feedback prompt builders: user gives natural language feedback, agent revises."""

from __future__ import annotations

import json
import re


def parse_note_feedback(feedback: str) -> tuple[int | None, str | None]:
    """If feedback is like 'index 13 make note X' or 'index 13 note: X', return (1-based index, note text); else (None, None)."""
    if not feedback or not feedback.strip():
        return None, None
    fb = feedback.strip()
    # index 13, make note reviewer will follow up | index 13 note: X | index 13 add note X
    m = re.search(
        r"index\s+(\d+)\s*[,:]?\s*(?:make\s+note|add\s+note|note|comment)\s*[:\s]*(.+)",
        fb,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        idx = int(m.group(1))
        note = m.group(2).strip()
        if note:
            return idx, note
    return None, None


# Phase 2 field names and allowed values (for parsing "change X to Y")
_P2_EXECUTION = {"manual", "automated", "hybrid"}
_P2_CONTROL_TYPE = {"preventive", "detective", "corrective"}


def parse_field_updates_p2(feedback: str) -> list[tuple[int, str, str]]:
    """Parse feedback for 'index N change execution type to X' / 'control_type to Y'. Returns [(1-based index, field_name, value), ...]."""
    if not feedback or not feedback.strip():
        return []
    fb = feedback.strip()
    out: list[tuple[int, str, str]] = []
    # index 14 change execution type to Automated | index 14 execution to Automated
    for m in re.finditer(
        r"index\s+(\d+)\s*[,:]?\s*(?:change\s+)?(?:execution(?:\s+type)?|execution_type)\s*(?::\s*|to\s+)(manual|automated|hybrid)",
        fb,
        re.IGNORECASE,
    ):
        idx, val = int(m.group(1)), m.group(2).lower()
        if val in _P2_EXECUTION:
            out.append((idx, "execution_type", val.capitalize()))
    for m in re.finditer(
        r"index\s+(\d+)\s*[,:]?\s*(?:change\s+)?(?:control(?:\s+type)?|control_type)\s*(?::\s*|to\s+)(preventive|detective|corrective)",
        fb,
        re.IGNORECASE,
    ):
        idx, val = int(m.group(1)), m.group(2).lower()
        if val in _P2_CONTROL_TYPE:
            out.append((idx, "control_type", val.capitalize()))
    return out


def feedback_needs_source_phase1(feedback: str) -> bool:
    """True only when user clearly asks to add a risk (then we send source doc). Modify/delete = no source, faster."""
    t = feedback.strip().lower()
    return "add" in t and any(x in t for x in ("risk", "new", "another"))


def feedback_needs_source_phase2(feedback: str) -> bool:
    """True only when user clearly asks to add a control mapping."""
    t = feedback.strip().lower()
    return "add" in t and any(x in t for x in ("control", "mapping", "new", "another"))


def feedback_needs_source_phase3(feedback: str) -> bool:
    """True only when user clearly asks to add a process mapping."""
    t = feedback.strip().lower()
    return "add" in t and any(x in t for x in ("process", "mapping", "new", "another"))


def parse_process_assignment_p3(feedback: str) -> tuple[int, str, str] | None:
    """Parse 'index 5 assign to P9, Employee Training' / 'index 5 should be assigned to p9, employee training'. Returns (1-based index, process_id, process_name) or None."""
    if not feedback or not feedback.strip():
        return None
    fb = feedback.strip()
    # index 5, this should be assigned to p9, employee training | index 5 assign to P9, Employee Training
    m = re.search(
        r"index\s+(\d+)\s*[,:]?\s*(?:this\s+should\s+be\s+)?assigned\s+to\s+(\S+)\s*[,:]?\s*(.+)",
        fb,
        re.IGNORECASE,
    )
    if m:
        idx = int(m.group(1))
        process_id = m.group(2).strip()
        process_name = m.group(3).strip()
        if process_id and process_name:
            return (idx, process_id, process_name)
    return None


def _chunks_to_source(chunks: list[dict], label: str) -> str:
    """Turn a list of chunk dicts (with 'text', 'source_name') into a single source block."""
    if not chunks:
        return ""
    parts = []
    for i, c in enumerate(chunks):
        name = c.get("source_name", "") or f"Chunk {i + 1}"
        text = c.get("text", "").strip()
        if text:
            parts.append(f"[{name}]\n{text}")
    if not parts:
        return ""
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 1 feedback
# ---------------------------------------------------------------------------

def build_phase_1_feedback_prompt(
    current_risks: list[dict],
    user_feedback: str,
    source_chunks: list[dict] | None = None,
) -> str:
    risks_with_index = [{**r, "Index": i} for i, r in enumerate(current_risks, 1)]
    risks_json = json.dumps(risks_with_index, indent=2)

    out = f"""Apply the user's feedback to this JSON. Return updated JSON only.

--- CURRENT RISKS (your "data" replaces this; table Row # = Index, 1-based) ---
{risks_json}

--- USER FEEDBACK ---
{user_feedback}

Rules: Use Index only. Find the specific index mentioned in the user's feedback, then apply changes only to that index. DELETE index N → remove that item ("data" has one fewer). MODIFY index N → change only that item, same count. NOTE for index N (e.g. "index 13 make note X") → set that item's "user_notes" and "feedback" to the note text. ADD new risk → only if SOURCE below provided; else skip. Message must state what you did and which index. Output: {{ "data": [ ... ], "message": "..." }}. Do not include Index in data. Changed items: user_status "Edited".
"""

    if source_chunks:
        source_block = _chunks_to_source(source_chunks, "Regulatory document")
        if source_block:
            out += f"""--- SOURCE (for ADD only) ---
{source_block}

"""

    out += "Return ONLY valid JSON."
    return out


# ---------------------------------------------------------------------------
# Phase 2 feedback
# ---------------------------------------------------------------------------

def build_phase_2_feedback_prompt(
    current_mappings: list[dict],
    user_feedback: str,
    control_chunks: list[dict] | None = None,
) -> str:
    mappings_with_index = [{**m, "Index": i} for i, m in enumerate(current_mappings, 1)]
    mappings_json = json.dumps(mappings_with_index, indent=2)

    out = f"""Apply the user's feedback to this JSON. Return updated JSON only.

--- CURRENT RISK-CONTROL MAPPINGS (your "data" replaces this; table Row # = Index, 1-based) ---
{mappings_json}

--- USER FEEDBACK ---
{user_feedback}

Rules: Use Index only. Find the specific index mentioned in the user's feedback, then apply changes only to that index. DELETE index N → remove that item ("data" has one fewer). MODIFY index N → change only that item, same count. NOTE for index N (e.g. "index 13 make note X") → set that item's "user_notes" and "feedback" to the note text. ADD mapping → only if CONTROL INVENTORY below provided; else skip. Message must state what you did and which index. Output: {{ "data": [ ... ], "message": "..." }}. Do not include Index in data. Changed items: user_status "Edited".
"""

    if control_chunks:
        inv_block = _chunks_to_source(control_chunks, "Control inventory")
        if inv_block:
            out += f"""--- CONTROL INVENTORY (for ADD only) ---
{inv_block}

"""

    out += "Return ONLY valid JSON."
    return out


# ---------------------------------------------------------------------------
# Phase 3 feedback
# ---------------------------------------------------------------------------

def build_phase_3_feedback_prompt(
    current_mappings: list[dict],
    user_feedback: str,
    process_chunks: list[dict] | None = None,
) -> str:
    mappings_with_index = [{**m, "Index": i} for i, m in enumerate(current_mappings, 1)]
    mappings_json = json.dumps(mappings_with_index, indent=2)

    out = f"""Apply the user's feedback to this JSON. Return updated JSON only.

--- CURRENT GOVERNANCE MAP (your "data" replaces this; table Row # = Index, 1-based) ---
{mappings_json}

--- USER FEEDBACK ---
{user_feedback}

Rules: Use Index only. Find the specific index mentioned in the user's feedback, then apply changes only to that index. DELETE index N → remove that item ("data" has one fewer). MODIFY index N → change only that item, same count. NOTE for index N (e.g. "index 13 make note X") → set that item's "user_notes" and "feedback" to the note text. ADD mapping → only if PROCESS DOCUMENTS below provided; else skip. Message must state what you did and which index. Output: {{ "data": [ ... ], "message": "..." }}. Do not include Index in data. Changed items: user_status "Edited".
"""

    if process_chunks:
        proc_block = _chunks_to_source(process_chunks, "Process documents")
        if proc_block:
            out += f"""--- PROCESS DOCUMENTS (for ADD only) ---
{proc_block}

"""

    out += "Return ONLY valid JSON."
    return out

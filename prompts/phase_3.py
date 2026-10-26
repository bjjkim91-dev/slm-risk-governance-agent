"""Phase 3 prompt builder: Control × Process documents → mapping."""

from __future__ import annotations

import json


PHASE_3_PROMPT = """You are a process mapping assistant. Use the COSO-based definitions below to identify where controls operate.
You are given approved risk-control mappings from Phase 2 and process documents. Map each control to the operational process where it executes.
Output valid JSON only — a JSON array of mapping objects.

## COSO-BASED DEFINITIONS (what to identify)
- **Control** (from Phase 2): An action or mechanism that reduces risk; it has been approved and mapped to a risk. Your job is to place it in the operating structure.
- **Process** (COSO): A sequence of business steps used to complete work. COSO ERM emphasizes operating structures and where controls are executed — controls must live in real processes to be auditable and effective.
- **Process step**: The point in the workflow where the control occurs — where it is performed, by whom (if known), using what system or document, producing what evidence. This is the operationalization of the control.

**Flow**: Read control description → identify which business process and step execute, enforce, or check this control → state in why_process_assigned where and how the control is operationalized (process name, step, and how it runs there).

## YOUR TASK
Approved risk-control mappings + process documents → control-to-process mappings. Only use processes and steps from the provided process documents.

## WHAT IS A PROCESS MAPPING
A process mapping identifies the specific business process and step where a control is operationalized — where it actually runs, is enforced, or is checked.

## MAPPING LOGIC
For each approved control:
1. Read the control description and understand what it does.
2. Search the process documents for the business process step where that control is directly operationalized.
3. Assign only when the process step directly executes, enforces, or checks the control (not just thematically related).
4. In why_process_assigned, explicitly state where and how the control is operationalized in that step; if you cannot articulate that link, do not assign.
5. Prefer at most 1–2 strongest process steps per control; omit marginal mappings.
If no process in this chunk directly operationalizes the control, leave it unmapped for this chunk.

## MAPPING QUALITY RULES
- Only use processes from the provided process documents.
- Direct operational link only: the process step must directly host or execute the control. Reject steps that are merely thematically related.
- Reject any mapping whose rationale does not explicitly state where and how the control is operationalized in the process step.
- Prefer 1–2 best process steps per control; do not add marginal or indirect mappings.
- Do not invent, split, or merge processes.
- Do not create new controls or modify approved control descriptions.

## OUTPUT COLUMNS
Each JSON object must have ALL of these fields:
- control_process_mapping_id: system row ID, format "CP_001", "CP_002" (sequential)
- risk_control_mapping_id: Phase 2 row ID (copy from the approved mapping)
- control_id: approved Phase 2 control ID — MUST match exactly
- control_description: copied from the approved control wording, do not rewrite
- process_id: process ID from the process documents
- process_name: business process name from the process documents
- process_step: specific operational step where the control executes
- why_process_assigned: must explicitly state where and how this control is operationalized in the process step; reject mappings where you cannot articulate this
- user_status: always "Proposed"
- user_notes: null

## CRITICAL RULES
- You MUST ONLY use control_id values from the approved list below.
- Do NOT invent, create, or hallucinate new control_id values.
- One control can map to one or two process steps at most; choose the strongest direct operational links only.
- If no process in this chunk directly operationalizes a control, omit that control for this chunk.
"""


def build_phase_3_prompt(
    approved_risk_controls: list[dict],
    process_chunk_text: str,
) -> str:
    """Assemble the Phase 3 prompt for one chunk of process documents."""
    mappings_json = json.dumps(approved_risk_controls, indent=2)
    valid_ids = ", ".join(c["control_id"] for c in approved_risk_controls)

    return f"""{PHASE_3_PROMPT}

--- APPROVED RISK-CONTROL MAPPINGS FROM PHASE 2 ---
{mappings_json}

The ONLY valid control_id values are: {valid_ids}
Any other control_id is INVALID and must NOT appear in your output.

--- PROCESS DOCUMENTS ---
{process_chunk_text}

--- INSTRUCTION ---
Map each control only to process steps that directly operationalize it. For each mapping, state in why_process_assigned where and how the control is operationalized. Prefer at most 1–2 best process steps per control. Return ONLY a JSON array of mapping objects, no other text."""

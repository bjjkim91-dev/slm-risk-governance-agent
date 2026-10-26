"""Build JSONL training files for P1, P2, P3 QLoRA fine-tuning.

For each of the 5 training sets:
  - Extracts text from source documents (PDF, XLSX, DOCX)
  - Builds the exact prompts the app would send to the LLM
  - Pairs each prompt with the expected JSON output
  - Writes ChatML-format JSONL files (one per phase)

Usage:
    python prepare_training_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion import extract_text
from prompts.phase_1 import build_phase_1_prompt
from prompts.phase_2 import build_phase_2_prompt
from prompts.phase_3 import build_phase_3_prompt

TRAINING_ROOT = Path(__file__).resolve().parent
TEST_DOCS_ROOT = PROJECT_ROOT / "data" / "test_docs"
EXPECTED_ROOT = TRAINING_ROOT  # training_reference/Set {1-5}/
OUTPUT_DIR = TRAINING_ROOT / "training_data"

SETS = ["Set 1", "Set 2", "Set 3", "Set 4", "Set 5"]

# Modelfile SYSTEM prompts (must match modelfiles_ft/Modelfile.coso_phase_{1,2,3})
SYSTEM_P1 = (
    "You are a compliance risk extraction and revision assistant. COSO-based definitions: obligation = what must be done per source; objective = what must be achieved; risk = possible failure if obligation not met (objective not achieved). Identify obligation, objective, and failure scenario; output one risk per unique obligation.\n"
    "You have two jobs:\n"
    "1. Extract risks from regulatory text as structured JSON.\n"
    "   Output one canonical risk per unique obligation only. Same obligation in (a) and (b) = one risk. Parent clause (v) with sub-clauses (A)(B) = at most two risks (for the distinct (A) and (B) obligations), not three. Fewer, merged risks are correct; do not list every sub-clause.\n"
    "   Risk statement: Failure to [action] may result in [outcome]. Assign severity and risk category.\n"
    "2. When given user feedback on existing risks, revise the risk list accordingly.\n"
    "   Add missed risks, modify as instructed. If the user says to remove a risk, EXCLUDE it from the output entirely.\n"
    "   Return the updated list: modified + unchanged items only, without removed ones.\n"
    "Output only valid JSON arrays."
)

SYSTEM_P2 = (
    "You are a control mapping and revision assistant. COSO-based: risk = possible failure affecting objectives; control = action/check/automation that reduces risk. Identify how each control directly addresses the failure (causal link); reject thematic-only matches.\n"
    "You have two jobs:\n"
    "1. Map approved risks to controls found in control documents.\n"
    "   Assign only controls that directly mitigate the failure in the risk statement; reject thematic-only matches.\n"
    "   In why_control_assigned, state how the control addresses that failure. Prefer 1–2 best controls per risk.\n"
    "   Assign control type (Preventive/Detective/Corrective) and execution type (Manual/Automated/Hybrid).\n"
    "2. When given user feedback on existing mappings, revise accordingly.\n"
    "   Add missed mappings, modify as instructed. If the user says to remove a mapping, EXCLUDE it from the output entirely.\n"
    "   Return the updated list: modified + unchanged items only, without removed ones.\n"
    "Output only valid JSON arrays."
)

SYSTEM_P3 = (
    "You are a process mapping and revision assistant. COSO-based: process = sequence of business steps; process step = where the control is executed or enforced. Identify the process and step that operationalize each control; state where and how.\n"
    "You have two jobs:\n"
    "1. Map approved controls to business processes from process documents.\n"
    "   Assign only when the process step directly operationalizes the control; reject thematic-only overlap.\n"
    "   In why_process_assigned, state where and how the control is operationalized. Prefer 1–2 best process steps per control.\n"
    "2. When given user feedback on existing mappings, revise accordingly.\n"
    "   Add missed mappings, modify as instructed. If the user says to remove a mapping, EXCLUDE it from the output entirely.\n"
    "   Return the updated list: modified + unchanged items only, without removed ones.\n"
    "Output only valid JSON arrays."
)


def _read_file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _find_file(folder: Path, pattern: str) -> Path | None:
    """Find first file matching a case-insensitive glob pattern."""
    for f in folder.iterdir():
        if f.is_file() and f.name.lower().endswith(pattern.lower()):
            return f
    return None


def _find_regulation_pdf(folder: Path) -> Path | None:
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() == ".pdf" and "CFR" in f.name:
            return f
    return None


def _extract_full_text(file_path: Path) -> str:
    """Extract all text from a file using the app's ingestion module."""
    raw = _read_file_bytes(file_path)
    return extract_text(raw, file_path.name)


def _load_expected(set_name: str, phase: int) -> list[dict]:
    path = EXPECTED_ROOT / set_name / f"phase_{phase}_expected.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_slim_risks(p1_expected: list[dict]) -> list[dict]:
    """Build the slim risk list that P2 prompt builder expects."""
    return [
        {
            "risk_id": r["risk_id"],
            "input_risk_mapping_id": r.get("input_risk_mapping_id", ""),
            "risk_statement": r["risk_statement"],
            "severity": r["severity"],
        }
        for r in p1_expected
    ]


def _build_slim_controls(p2_expected: list[dict]) -> list[dict]:
    """Build the slim control list that P3 prompt builder expects."""
    return [
        {
            "control_id": rc["control_id"],
            "risk_control_mapping_id": rc.get("risk_control_mapping_id", ""),
            "control_description": rc.get("control_description", ""),
        }
        for rc in p2_expected
    ]


def _conversation(system: str, user: str, assistant: str) -> dict:
    return {
        "conversations": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


def _write_jsonl(records: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  Wrote {len(records)} examples to {path}")


def prepare():
    p1_records: list[dict] = []
    p2_records: list[dict] = []
    p3_records: list[dict] = []

    for set_name in SETS:
        test_dir = TEST_DOCS_ROOT / set_name
        if not test_dir.exists():
            print(f"WARN: {test_dir} not found, skipping")
            continue

        print(f"\n--- {set_name} ---")

        # --- Phase 1: Regulation PDF -> risks ---
        reg_pdf = _find_regulation_pdf(test_dir)
        if not reg_pdf:
            print(f"  WARN: No regulation PDF found in {test_dir}")
        else:
            reg_text = _extract_full_text(reg_pdf)
            p1_expected = _load_expected(set_name, 1)
            user_prompt = build_phase_1_prompt(reg_text, source_filename=reg_pdf.name)
            assistant_response = json.dumps(p1_expected, indent=2, ensure_ascii=False)
            p1_records.append(_conversation(SYSTEM_P1, user_prompt, assistant_response))
            print(f"  P1: {reg_pdf.name} -> {len(p1_expected)} risks")

        # --- Phase 2: Approved risks + Control Inventory -> risk-control mappings ---
        ctrl_file = _find_file(test_dir, ".xlsx")
        ctrl_candidates = [f for f in test_dir.iterdir()
                           if f.is_file() and "control" in f.name.lower() and f.suffix.lower() in (".xlsx", ".xls")]
        ctrl_file = ctrl_candidates[0] if ctrl_candidates else None
        if not ctrl_file:
            print(f"  WARN: No Control Inventory found in {test_dir}")
        else:
            ctrl_text = _extract_full_text(ctrl_file)
            p1_expected = _load_expected(set_name, 1)
            p2_expected = _load_expected(set_name, 2)
            slim_risks = _build_slim_risks(p1_expected)
            user_prompt = build_phase_2_prompt(slim_risks, ctrl_text)
            assistant_response = json.dumps(p2_expected, indent=2, ensure_ascii=False)
            p2_records.append(_conversation(SYSTEM_P2, user_prompt, assistant_response))
            print(f"  P2: {ctrl_file.name} + {len(slim_risks)} risks -> {len(p2_expected)} mappings")

        # --- Phase 3: Approved risk-controls + Process narratives -> control-process mappings ---
        proc_candidates = [f for f in test_dir.iterdir()
                           if f.is_file() and "process" in f.name.lower() and f.suffix.lower() == ".docx"]
        proc_file = proc_candidates[0] if proc_candidates else None
        if not proc_file:
            print(f"  WARN: No Process narratives found in {test_dir}")
        else:
            proc_text = _extract_full_text(proc_file)
            p2_expected = _load_expected(set_name, 2)
            p3_expected = _load_expected(set_name, 3)
            slim_controls = _build_slim_controls(p2_expected)
            user_prompt = build_phase_3_prompt(slim_controls, proc_text)
            assistant_response = json.dumps(p3_expected, indent=2, ensure_ascii=False)
            p3_records.append(_conversation(SYSTEM_P3, user_prompt, assistant_response))
            print(f"  P3: {proc_file.name} + {len(slim_controls)} controls -> {len(p3_expected)} mappings")

    # Write JSONL files
    print("\n--- Writing JSONL ---")
    _write_jsonl(p1_records, OUTPUT_DIR / "p1_train.jsonl")
    _write_jsonl(p2_records, OUTPUT_DIR / "p2_train.jsonl")
    _write_jsonl(p3_records, OUTPUT_DIR / "p3_train.jsonl")

    print(f"\nDone. {len(p1_records)} P1 + {len(p2_records)} P2 + {len(p3_records)} P3 examples.")


if __name__ == "__main__":
    prepare()

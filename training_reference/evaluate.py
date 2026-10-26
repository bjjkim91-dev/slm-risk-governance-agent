"""Evaluate fine-tuned models by running them on the test sets via Ollama.

For each test set and phase, sends the same prompt the app would send
and compares the model's output to the expected JSON.

Metrics:
  - schema_valid:  response is valid JSON with all required fields
  - count_match:   number of output rows matches expected
  - id_recall:     fraction of expected IDs present in model output
  - field_fill:    fraction of non-empty required fields

Usage:
    python evaluate.py                          # all phases, all sets
    python evaluate.py --phase 1                # phase 1 only
    python evaluate.py --phase 1 --set 1        # phase 1, set 1 only
    python evaluate.py --model qwen2.5:7b       # use base (non-ft) model
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion import extract_text
from prompts.phase_1 import build_phase_1_prompt
from prompts.phase_2 import build_phase_2_prompt
from prompts.phase_3 import build_phase_3_prompt
from llm_client import parse_json_response

TRAINING_ROOT = Path(__file__).resolve().parent
TEST_DOCS_ROOT = PROJECT_ROOT / "data" / "test_docs"
EXPECTED_ROOT = TRAINING_ROOT

OLLAMA_URL = "http://localhost:11434/api/generate"

SETS = ["Set 1", "Set 2", "Set 3", "Set 4", "Set 5"]

DEFAULT_MODELS = {1: "coso_phase_1", 2: "coso_phase_2", 3: "coso_phase_3"}

P1_REQUIRED = ["risk_id", "risk_statement", "risk_category", "severity", "why_identified"]
P2_REQUIRED = ["risk_id", "risk_statement", "control_id", "control_description", "why_control_assigned", "control_type"]
P3_REQUIRED = ["control_id", "control_description", "process_id", "process_name", "process_step", "why_process_assigned"]

REQUIRED_FIELDS = {1: P1_REQUIRED, 2: P2_REQUIRED, 3: P3_REQUIRED}
ID_FIELD = {1: "risk_id", 2: "risk_id", 3: "control_id"}


def _read_file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _find_regulation_pdf(folder: Path) -> Path | None:
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() == ".pdf" and "CFR" in f.name:
            return f
    return None


def _find_control_inventory(folder: Path) -> Path | None:
    for f in folder.iterdir():
        if f.is_file() and "control" in f.name.lower() and f.suffix.lower() in (".xlsx", ".xls"):
            return f
    return None


def _find_process_doc(folder: Path) -> Path | None:
    for f in folder.iterdir():
        if f.is_file() and "process" in f.name.lower() and f.suffix.lower() == ".docx":
            return f
    return None


def _extract_full_text(file_path: Path) -> str:
    return extract_text(_read_file_bytes(file_path), file_path.name)


def _load_expected(set_name: str, phase: int) -> list[dict]:
    path = EXPECTED_ROOT / set_name / f"phase_{phase}_expected.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _call_ollama(prompt: str, model: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 8192, "temperature": 0.3},
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json().get("response", "")


def _build_prompt(phase: int, set_name: str) -> str | None:
    test_dir = TEST_DOCS_ROOT / set_name

    if phase == 1:
        pdf = _find_regulation_pdf(test_dir)
        if not pdf:
            return None
        text = _extract_full_text(pdf)
        return build_phase_1_prompt(text, source_filename=pdf.name)

    elif phase == 2:
        ctrl = _find_control_inventory(test_dir)
        if not ctrl:
            return None
        ctrl_text = _extract_full_text(ctrl)
        p1_expected = _load_expected(set_name, 1)
        slim_risks = [
            {"risk_id": r["risk_id"], "input_risk_mapping_id": r.get("input_risk_mapping_id", ""),
             "risk_statement": r["risk_statement"], "severity": r["severity"]}
            for r in p1_expected
        ]
        return build_phase_2_prompt(slim_risks, ctrl_text)

    elif phase == 3:
        proc = _find_process_doc(test_dir)
        if not proc:
            return None
        proc_text = _extract_full_text(proc)
        p2_expected = _load_expected(set_name, 2)
        slim_controls = [
            {"control_id": rc["control_id"], "risk_control_mapping_id": rc.get("risk_control_mapping_id", ""),
             "control_description": rc.get("control_description", "")}
            for rc in p2_expected
        ]
        return build_phase_3_prompt(slim_controls, proc_text)

    return None


def _score(phase: int, model_output: list[dict], expected: list[dict]) -> dict:
    """Compute evaluation metrics."""
    required = REQUIRED_FIELDS[phase]
    id_field = ID_FIELD[phase]

    schema_valid = all(
        all(f in row for f in required) for row in model_output
    ) if model_output else False

    count_match = len(model_output) == len(expected)

    expected_ids = {r[id_field] for r in expected}
    model_ids = {r.get(id_field, "") for r in model_output}
    id_recall = len(expected_ids & model_ids) / len(expected_ids) if expected_ids else 1.0

    total_fields = 0
    filled_fields = 0
    for row in model_output:
        for f in required:
            total_fields += 1
            val = row.get(f, "")
            if val and str(val).strip():
                filled_fields += 1
    field_fill = filled_fields / total_fields if total_fields else 0.0

    return {
        "schema_valid": schema_valid,
        "count_expected": len(expected),
        "count_actual": len(model_output),
        "count_match": count_match,
        "id_recall": round(id_recall, 3),
        "field_fill": round(field_fill, 3),
    }


def evaluate(phases: list[int], sets: list[str], model_override: str | None = None):
    results = []

    for phase in phases:
        model = model_override or DEFAULT_MODELS[phase]
        print(f"\n{'='*60}")
        print(f"  Phase {phase} — model: {model}")
        print(f"{'='*60}")

        for set_name in sets:
            print(f"\n  {set_name}:")
            prompt = _build_prompt(phase, set_name)
            if not prompt:
                print(f"    SKIP: could not build prompt")
                continue

            expected = _load_expected(set_name, phase)
            print(f"    Expected: {len(expected)} rows")

            t0 = time.time()
            try:
                raw = _call_ollama(prompt, model)
                parsed = parse_json_response(raw)
            except Exception as e:
                print(f"    ERROR: {e}")
                results.append({"phase": phase, "set": set_name, "error": str(e)})
                continue
            elapsed = time.time() - t0

            if isinstance(parsed, dict):
                parsed = [parsed]

            scores = _score(phase, parsed, expected)
            scores["phase"] = phase
            scores["set"] = set_name
            scores["elapsed_s"] = round(elapsed, 1)
            results.append(scores)

            status = "PASS" if scores["schema_valid"] and scores["count_match"] else "CHECK"
            print(f"    {status} | rows: {scores['count_actual']}/{scores['count_expected']} "
                  f"| id_recall: {scores['id_recall']} | field_fill: {scores['field_fill']} "
                  f"| {elapsed:.1f}s")

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    for r in results:
        if "error" in r:
            print(f"  P{r['phase']} {r['set']}: ERROR — {r['error']}")
        else:
            flag = "OK" if r["schema_valid"] and r["count_match"] else "!!"
            print(f"  P{r['phase']} {r['set']}: [{flag}] "
                  f"rows={r['count_actual']}/{r['count_expected']} "
                  f"id_recall={r['id_recall']} field_fill={r['field_fill']}")

    # Write results JSON
    out_path = TRAINING_ROOT / "eval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate fine-tuned RGA models")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3])
    parser.add_argument("--set", type=int, choices=[1, 2, 3, 4, 5])
    parser.add_argument("--model", type=str, help="Override model name (e.g. qwen2.5:7b for the base model)")
    args = parser.parse_args()

    phases = [args.phase] if args.phase else [1, 2, 3]
    sets = [f"Set {args.set}"] if args.set else SETS

    evaluate(phases, sets, args.model)


if __name__ == "__main__":
    main()

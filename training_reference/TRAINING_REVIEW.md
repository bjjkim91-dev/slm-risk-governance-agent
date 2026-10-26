# Training Set and Expected Output Review

## Pipeline Overview

| Step | Script | Input | Output |
|------|--------|--------|--------|
| Build training data | `prepare_training_data.py` | For each Set 1–5: source docs + `build_phase_N_prompt(...)` + `phase_N_expected.json` | `training_data/p1_train.jsonl`, `p2_train.jsonl`, `p3_train.jsonl` |
| Train | Adapters (QLoRA) / GGUF | JSONL + base model | `adapters/phase_N/`, `gguf/coso_phase_N.gguf` |
| Register | `register_coso_models.py` | GGUF + Modelfile | Ollama models `coso_phase_1`, `coso_phase_2`, `coso_phase_3` |

## Training Inputs (what the model sees)

- **Phase 1**: Full regulatory document text (single concatenated string) + source filename. One example per set (5 total). Prompt from `prompts/phase_1.py` `build_phase_1_prompt(reg_text, reg_pdf.name)`.
- **Phase 2**: Full control document text (single string) + slim risk list from **phase_1_expected.json** (risk_id, input_risk_mapping_id, risk_statement, severity). One example per set. Prompt from `prompts/phase_2.py` `build_phase_2_prompt(slim_risks, ctrl_text)`.
- **Phase 3**: Full process document text (single string) + slim control list from **phase_2_expected.json** (control_id, risk_control_mapping_id, control_description). One example per set. Prompt from `prompts/phase_3.py` `build_phase_3_prompt(slim_controls, proc_text)`.

## Expected Outputs (ground truth)

Stored under `training_reference/Set N/phase_{1,2,3}_expected.json`.

- **Phase 1**: One risk per **requirement theme**; concise risk statements; `requirement_theme` / `source_ref` align with that theme. No procedural/housekeeping-only risks (e.g. “make copy available”) unless the labels treat them as distinct. Sets have 5–8+ risks depending on regulation.
- **Phase 2**: Risk–control mappings; `why_control_assigned` in the expected files is a short template sentence naming the requirement theme the control addresses. The app prompt asks for a fuller causal rationale at inference; the labels can be rewritten in that style when regenerating training data.
- **Phase 3**: Control–process mappings; `why_process_assigned` names the process step (Pn) from the narrative where the control is operationalized. One process step per control per row; the same control can appear in several rows (different process steps).

## Train vs Inference Mismatch

- **Training**: Each phase sees the **full** document (regulatory, control, or process) in one user message.
- **Inference**: The app **chunks** documents (e.g. 3000 chars per chunk; control docs 6000). Each phase runs **one LLM call per chunk** and results are merged/deduped.

So the model is trained to produce a single consolidated output from a full document, but at inference it only ever sees one chunk at a time. That can contribute to Phase 1 over-splitting or duplicate risks across chunks. Mitigations: stronger “canonical risk set” and dedup rules in the Phase 1 prompt (done); optionally chunk training in a future run so each example is one chunk → one partial output.

## Alignment Checklist

- [x] Phase 1 prompt: canonical risk set, one risk per theme, no procedural-only risks (aligned with expected).
- [x] Phase 2 prompt: direct mitigation only; rationale must address failure; 1–2 controls per risk (stricter than current expected wording; expected rationales can be updated when rebuilding training data).
- [x] Phase 3 prompt: direct operational link; rationale must state where control is operationalized; prefer 1–2 processes per control (aligned with expected structure).
- [x] `prepare_training_data.py` SYSTEM prompts: updated to match the above so training and app prompts are consistent.
- [x] Modelfiles (coso_phase_1/2/3): SYSTEM text updated to match so registered models reflect the same behavior.

## Regenerating Training Data

After changing phase prompts:

1. Run `python prepare_training_data.py` so JSONL uses the latest `build_phase_N_prompt` and SYSTEM text.
2. Retrain adapters / export GGUF if you want the model to reinforce the new instructions.
3. Re-register with `python register_coso_models.py` if Modelfiles changed.

Expected JSON files (`phase_N_expected.json`) are hand-written labels; they are not auto-generated. Update them manually if you want training targets to match stricter rationales (e.g. causal-link style for P2).

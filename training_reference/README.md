# Training pipeline

The fine-tuning workflow for the full system: three QLoRA adapters on Qwen2.5-7B-Instruct, one per phase, packaged as Ollama models. The app in the parent folder runs on `gemma2:2b` out of the box; point `PHASE_MODELS` in `config.py` at the models produced here to use the fine-tuned ones.

## What is here

| Item | Role |
|------|------|
| `prepare_training_data.py` | Builds ChatML JSONL per phase from the document sets in `data/test_docs/` and the expected outputs here, using the app's own prompt builders, so training and inference see the same instructions |
| `training_data/` | The fine-tuning JSONL built by `prepare_training_data.py`: `p1_train.jsonl`, `p2_train.jsonl`, `p3_train.jsonl`, one record per set per phase |
| `Set 1` to `Set 5/` | Expected phase outputs (labels) for the five document sets, written to the same methodology the prompts enforce |
| `train_phase.py` | QLoRA fine-tuning for phase 1, 2 or 3: 4-bit base, LoRA adapters, TRL `SFTTrainer` |
| `export_to_ollama.py` | Merges an adapter into the base and creates an Ollama model from a Modelfile |
| `register_coso_models.py` | Registers exported GGUF phase models with Ollama |
| `modelfiles_ft/` | Ollama Modelfiles with the per-phase system prompts |
| `evaluate.py` | Replays the sets through Ollama and scores schema validity, row count, ID recall and field fill against the expected JSON |
| `rebuild_sample_sets.py` | Regenerates the input documents of a set from the training records |
| `TRAINING_REVIEW.md` | Notes from the training process and the train-versus-inference mismatch |

## The five document sets

Each set is one regulation, one control inventory and one process narrative, with expected outputs for all three phases.

| Set | Regulation (public-domain US federal text) | Process narrative |
|---|---|---|
| 1 | 31 CFR 1020.220, customer identification programs for banks | Customer onboarding and identity verification |
| 2 | 31 CFR 1020.210, anti-money-laundering program requirements | AML compliance monitoring and customer due diligence |
| 3 | 31 CFR 1020.320, suspicious transaction reports | Suspicious activity detection, investigation and SAR filing |
| 4 | 31 CFR 1010.311, currency transaction reports | Currency transaction detection and CTR filing |
| 5 | 31 CFR 1010.230, beneficial ownership of legal entity customers | Legal entity onboarding and beneficial ownership |

Control inventories and process narratives are synthetic. Sets 2 and 3 are the original files; the input documents for sets 1, 4 and 5 were rebuilt from the text embedded in the training records with `rebuild_sample_sets.py`, which is why those regulations are plain-text PDFs.

## Not here

The trained LoRA adapters (about 1.3 GB) and the merged GGUF exports (tens of GB) are too large to publish. Train them with the steps below.

## Steps

```bash
pip install -r training_reference/requirements_training.txt
python training_reference/prepare_training_data.py     # data/test_docs + Set N expected -> training_data/*.jsonl
python training_reference/train_phase.py --phase 1     # repeat for 2 and 3; needs a CUDA GPU
python training_reference/export_to_ollama.py --phase 1
python training_reference/evaluate.py --phase 1
```

Scripts expect to live in this folder inside the project root, with `ingestion` and `prompts` importable from the parent.

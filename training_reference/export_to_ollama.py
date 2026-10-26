"""Export fine-tuned LoRA adapters to Ollama.

Creates Ollama models that load the LoRA adapter on top of the base
qwen2.5:7b model.  Ollama supports direct safetensors adapter import,
so no GGUF conversion is needed.

Usage:
    python export_to_ollama.py              # all phases
    python export_to_ollama.py --phase 1    # single phase

After export, the app's config.py PHASE_MODELS should be updated to
point to the fine-tuned model names (rga-phase1-ft, etc.).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TRAINING_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TRAINING_ROOT.parent
ADAPTERS_DIR = TRAINING_ROOT / "adapters"
MODELFILES_DIR = TRAINING_ROOT / "modelfiles_ft"

PHASES = [1, 2, 3]

# the same per-phase system text as prepare_training_data.py and modelfiles_ft/Modelfile.coso_phase_*
from prepare_training_data import SYSTEM_P1, SYSTEM_P2, SYSTEM_P3  # noqa: E402

SYSTEM_PROMPTS = {1: SYSTEM_P1, 2: SYSTEM_P2, 3: SYSTEM_P3}


def _adapter_dir(phase: int) -> Path:
    return ADAPTERS_DIR / f"phase_{phase}" / "final"


def _merge_adapter_and_save(phase: int) -> Path:
    """Merge LoRA adapter with base Qwen model and save; return path to merged dir."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    adapter_path = _adapter_dir(phase)
    if not adapter_path.exists():
        raise FileNotFoundError(
            f"Adapter not found at {adapter_path}. Run train_phase.py --phase {phase} first."
        )

    merged_dir = TRAINING_ROOT / "merged" / f"phase_{phase}"
    merged_dir.mkdir(parents=True, exist_ok=True)
    if (merged_dir / "config.json").exists():
        print(f"  Merged model already at {merged_dir}, skipping merge.")
        return merged_dir

    print(f"  Merging adapter with base model (this may take a few minutes)...")
    base_name = "Qwen/Qwen2.5-7B-Instruct"
    tokenizer = AutoTokenizer.from_pretrained(base_name, trust_remote_code=True)
    # Use single device to avoid accelerate get_balanced_memory "unhashable type: set" bug
    model = AutoModelForCausalLM.from_pretrained(
        base_name,
        torch_dtype=torch.bfloat16,
        device_map="cuda:0",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(model, str(adapter_path), device_map="cuda:0")
    model = model.merge_and_unload()
    model.save_pretrained(merged_dir, safe_serialization=True)
    tokenizer.save_pretrained(merged_dir)
    print(f"  Saved merged model to {merged_dir}")
    return merged_dir


def _write_modelfile(phase: int, from_path: str) -> Path:
    """Write an Ollama Modelfile. from_path is the FROM argument (e.g. path to merged dir or GGUF)."""
    MODELFILES_DIR.mkdir(parents=True, exist_ok=True)
    modelfile_path = MODELFILES_DIR / f"Modelfile.phase{phase}"
    system_prompt = SYSTEM_PROMPTS[phase]
    from_path_clean = from_path.replace("\\", "/")
    content = f'''FROM {from_path_clean}

SYSTEM """
{system_prompt}
"""

PARAMETER temperature 0.3
PARAMETER num_ctx 32768
PARAMETER num_predict 8192
'''
    modelfile_path.write_text(content, encoding="utf-8")
    return modelfile_path


def _register_with_ollama(phase: int, modelfile_path: Path):
    """Run 'ollama create' to register the fine-tuned model."""
    model_name = f"rga-phase{phase}-ft"
    print(f"  Registering {model_name} with Ollama...")

    result = subprocess.run(
        ["ollama", "create", model_name, "-f", str(modelfile_path)],
        capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace",
    )

    if result.returncode == 0:
        print(f"  OK: {model_name} registered successfully.")
    else:
        print(f"  ERROR registering {model_name}:")
        print(f"    stdout: {result.stdout.strip()}")
        print(f"    stderr: {result.stderr.strip()}")
        return False
    return True


def _update_config(phases: list[int]):
    """Print the config.py PHASE_MODELS update the user should apply."""
    print("\n--- config.py update ---")
    print("Update PHASE_MODELS in config.py to use fine-tuned models:\n")
    print("PHASE_MODELS = {")
    for p in [1, 2, 3]:
        name = f"rga-phase{p}-ft" if p in phases else f"rga-phase{p}"
        print(f'    "phase_{p}": "{name}",')
    print('    "summary": "rga-summary",')
    print("}")


def export(phases: list[int]):
    print(f"Exporting phases: {phases}\n")
    success = []

    for phase in phases:
        print(f"\n--- Phase {phase} ---")
        try:
            merged_dir = _merge_adapter_and_save(phase)
            from_arg = str(merged_dir.resolve())
            modelfile_path = _write_modelfile(phase, from_arg)
            print(f"  Modelfile: {modelfile_path}")
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
            continue
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        if _register_with_ollama(phase, modelfile_path):
            success.append(phase)

    if success:
        _update_config(success)
        print(f"\nExport complete. Phases registered: {success}")
    else:
        print("\nNo phases were exported. Ollama may not support Qwen from HF dir.")
        print("You can convert merged models to GGUF with llama.cpp convert_hf_to_gguf.py")
        print("then use: FROM /path/to/model.gguf in the Modelfile.")


def main():
    parser = argparse.ArgumentParser(description="Export LoRA adapters to Ollama")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3],
                        help="Export a single phase (default: all)")
    args = parser.parse_args()

    phases = [args.phase] if args.phase else PHASES
    export(phases)


if __name__ == "__main__":
    main()

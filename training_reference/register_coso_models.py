"""Register coso_phase_1, coso_phase_2, coso_phase_3 with Ollama on this machine.

Patches the FROM path in each Modelfile to point at this project's
training_reference/gguf/ folder, then runs `ollama create`.

Run from project root:
    python training_reference/register_coso_models.py

Requires:
  - Ollama running (ollama serve)
  - GGUF files present: training_reference/gguf/coso_phase_1.gguf, etc.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

TRAINING_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TRAINING_ROOT.parent
GGUF_DIR = TRAINING_ROOT / "gguf"
MODELFILES_DIR = TRAINING_ROOT / "modelfiles_ft"

MODELS = [
    ("coso_phase_1", "Modelfile.coso_phase_1"),
    ("coso_phase_2", "Modelfile.coso_phase_2"),
    ("coso_phase_3", "Modelfile.coso_phase_3"),
]


def main() -> int:
    if not GGUF_DIR.exists():
        print(f"ERROR: GGUF directory not found: {GGUF_DIR}")
        print("Copy coso_phase_1.gguf, coso_phase_2.gguf, coso_phase_3.gguf into that folder.")
        return 1

    # Use forward slashes for FROM path (Ollama accepts on Windows too)
    gguf_path_base = GGUF_DIR.as_posix()

    for model_name, modelfile_name in MODELS:
        gguf_file = GGUF_DIR / f"{model_name}.gguf"
        if not gguf_file.exists():
            print(f"SKIP: {gguf_file.name} not found")
            continue

        modelfile_src = MODELFILES_DIR / modelfile_name
        if not modelfile_src.exists():
            print(f"SKIP: {modelfile_name} not found")
            continue

        content = modelfile_src.read_text(encoding="utf-8")
        from_line = f"FROM {gguf_path_base}/{model_name}.gguf"
        lines = content.splitlines()
        if not lines:
            print(f"SKIP: {modelfile_name} is empty")
            continue
        lines[0] = from_line
        patched = "\n".join(lines) + "\n"

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".Modelfile",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(patched)
            temp_path = f.name

        print(f"Registering {model_name}...")
        result = subprocess.run(
            ["ollama", "create", model_name, "-f", temp_path],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        Path(temp_path).unlink(missing_ok=True)

        if result.returncode == 0:
            print(f"  OK: {model_name}")
        else:
            print(f"  FAILED: {model_name}")
            if result.stderr:
                print(result.stderr.strip())
            return 1

    print("\nDone. Run: ollama list")
    return 0


if __name__ == "__main__":
    sys.exit(main())

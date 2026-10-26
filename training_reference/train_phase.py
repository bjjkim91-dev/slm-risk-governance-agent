"""QLoRA fine-tuning for a single RGA phase (1, 2, or 3).

Trains a LoRA adapter on Qwen2.5 7B using the phase-specific JSONL
produced by prepare_training_data.py.

Usage:
    python train_phase.py --phase 1
    python train_phase.py --phase 2
    python train_phase.py --phase 3
    python train_phase.py --phase 1 --epochs 5 --lr 1e-4

Requires the training venv (training_reference/train_venv).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

TRAINING_ROOT = Path(__file__).resolve().parent
DATA_DIR = TRAINING_ROOT / "training_data"
ADAPTERS_DIR = TRAINING_ROOT / "adapters"

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"

PHASE_FILES = {
    1: "p1_train.jsonl",
    2: "p2_train.jsonl",
    3: "p3_train.jsonl",
}


def load_dataset_from_jsonl(phase: int) -> Dataset:
    path = DATA_DIR / PHASE_FILES[phase]
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line.strip()))
    return Dataset.from_list(records)


def format_conversation(example: dict, tokenizer) -> str:
    """Apply the model's chat template to a training example."""
    messages = example["conversations"]
    return tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False
    )


def train(phase: int, epochs: int = 3, lr: float = 2e-4, max_seq_length: int = 4096):
    print(f"\n{'='*60}")
    print(f"  QLoRA Fine-Tuning - Phase {phase}")
    print(f"  Base model: {BASE_MODEL}")
    print(f"  Epochs: {epochs}  LR: {lr}  Max seq: {max_seq_length}")
    print(f"{'='*60}\n")

    # Load dataset
    dataset = load_dataset_from_jsonl(phase)
    print(f"Training examples: {len(dataset)}")

    # Quantization config (4-bit NF4)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Load model in 4-bit
    print("Loading model in 4-bit...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model = prepare_model_for_kbit_training(model)

    # LoRA config
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Format dataset with chat template
    def _format(example):
        return {"text": format_conversation(example, tokenizer)}

    formatted_dataset = dataset.map(_format, remove_columns=dataset.column_names)

    # Output directory
    output_dir = ADAPTERS_DIR / f"phase_{phase}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Training arguments
    training_args = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=1,
        save_strategy="epoch",
        save_total_limit=2,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="adamw_8bit",
        max_length=max_seq_length,
        dataset_text_field="text",
        report_to="none",
        seed=42,
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=formatted_dataset,
        processing_class=tokenizer,
    )

    # Train
    print("\nStarting training...")
    train_result = trainer.train()

    # Save final adapter
    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    print(f"\nTraining complete for Phase {phase}.")
    print(f"  Loss: {train_result.training_loss:.4f}")
    print(f"  Adapter saved to: {final_dir}")

    # Free GPU memory
    del model, trainer
    torch.cuda.empty_cache()

    return final_dir


def main():
    parser = argparse.ArgumentParser(description="QLoRA fine-tuning for RGA phases")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2, 3])
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    args = parser.parse_args()

    train(args.phase, args.epochs, args.lr, args.max_seq_length)


if __name__ == "__main__":
    main()

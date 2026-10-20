"""RTX/CUDA QLoRA trainer for Generator A.

Uses the repository's V5 training split by default. Prompt tokens are masked
from the causal-LM loss, so training optimizes the assistant completion rather
than memorizing the system/user prompt. This script intentionally targets the
teammate's CUDA + bitsandbytes RTX workflow; it is not the MPS training path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = os.environ.get("QWEN_MODEL_ID", "Qwen/Qwen2.5-Coder-1.5B-Instruct")
TRAIN_DATA_PATH = Path(os.environ.get(
    "GENERATOR_A_TRAIN_DATA",
    str(ROOT / "data/training_v3/generator_a_train_v5.jsonl"),
))
OUTPUT_DIR = Path(os.environ.get(
    "GENERATOR_A_OUTPUT_DIR",
    str(ROOT / "models/checkpoints/generator_a_qwen_1.5b_rtx"),
))
SYSTEM_PROMPT = (
    "You are an expert C source code obfuscator. Obfuscate the provided C "
    "code while strictly maintaining functional behavior. Return only the "
    "complete transformed C source code, without Markdown fences or commentary."
)


class ObfuscationDataset(Dataset):
    """Chat-formatted examples with loss applied only to assistant tokens."""

    def __init__(self, data_path: Path, tokenizer: Any, max_length: int = 1024):
        if not data_path.is_file():
            raise FileNotFoundError(
                f"Training dataset not found: {data_path}\n"
                "Expected data/training_v3/generator_a_train_v5.jsonl."
            )
        self.examples: list[dict[str, list[int]]] = []
        with data_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                item = json.loads(line)
                if not isinstance(item.get("input_text"), str) or not isinstance(
                    item.get("target_text"), str
                ):
                    raise ValueError(
                        f"{data_path}:{line_number}: input_text and target_text "
                        "must both be strings."
                    )

                prompt_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": item["input_text"]},
                ]
                full_messages = prompt_messages + [
                    {"role": "assistant", "content": item["target_text"]}
                ]

                prompt_ids = tokenizer.apply_chat_template(
                    prompt_messages,
                    tokenize=True,
                    add_generation_prompt=True,
                )
                full_ids = tokenizer.apply_chat_template(
                    full_messages,
                    tokenize=True,
                    add_generation_prompt=False,
                )
                if isinstance(prompt_ids, dict):
                    prompt_ids = prompt_ids["input_ids"]
                if isinstance(full_ids, dict):
                    full_ids = full_ids["input_ids"]
                prompt_ids = list(prompt_ids)
                full_ids = list(full_ids)

                # Usually the prompt token sequence is an exact prefix of the
                # full conversation. Use the common prefix length defensively.
                prefix_len = 0
                for prompt_token, full_token in zip(prompt_ids, full_ids):
                    if prompt_token != full_token:
                        break
                    prefix_len += 1
                if prefix_len >= len(full_ids):
                    raise ValueError(
                        f"{data_path}:{line_number}: no assistant target tokens "
                        "remain after masking the prompt."
                    )

                full_ids = full_ids[:max_length]
                if prefix_len >= len(full_ids):
                    raise ValueError(
                        f"{data_path}:{line_number}: prompt consumes the entire "
                        f"{max_length}-token sequence; increase max_length."
                    )
                labels = [-100] * prefix_len + full_ids[prefix_len:]
                self.examples.append({
                    "input_ids": full_ids,
                    "attention_mask": [1] * len(full_ids),
                    "labels": labels,
                })

        if not self.examples:
            raise ValueError(f"No usable training records found in {data_path}")

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, list[int]]:
        return self.examples[index]


def train() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError(
            "This script is the RTX/CUDA QLoRA trainer and requires CUDA. "
            "Do not run it on the M1 Mac. Run it on the teammate's Windows/Linux "
            "machine with the RTX GPU, or use the already-trained adapter."
        )
    try:
        import bitsandbytes  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "bitsandbytes is required for the RTX 4-bit QLoRA setup."
        ) from exc

    if not TRAIN_DATA_PATH.is_file():
        raise FileNotFoundError(
            f"Dataset not found: {TRAIN_DATA_PATH}. Available V5 dataset should be "
            "data/training_v3/generator_a_train_v5.jsonl."
        )

    print(f"Model: {MODEL_ID}")
    print(f"Training data: {TRAIN_DATA_PATH}")
    print(f"Output: {OUTPUT_DIR}")
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=quant_config,
        device_map={"": torch.cuda.current_device()},
        torch_dtype=torch.float16,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    train_dataset = ObfuscationDataset(TRAIN_DATA_PATH, tokenizer)
    print(f"Loaded {len(train_dataset)} training examples with prompt masking.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        max_steps=300,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=10,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        report_to="none",
        remove_unused_columns=False,
        gradient_checkpointing=True,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            pad_to_multiple_of=8,
            label_pad_token_id=-100,
            return_tensors="pt",
        ),
    )
    trainer.train()

    adapter_path = OUTPUT_DIR / "final_adapter"
    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"Training complete. Adapter saved to: {adapter_path}")


if __name__ == "__main__":
    train()

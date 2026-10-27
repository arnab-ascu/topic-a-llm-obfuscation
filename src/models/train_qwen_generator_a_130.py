import json
import torch
from pathlib import Path
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
    TrainingArguments, Trainer, DataCollatorForSeq2Seq
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
OUTPUT_DIR = "models/checkpoints/generator_a_qwen_1.5b_130_rtx"
TRAIN_DATA_PATH = "data/training_expanded/train_entropy_ioccc.jsonl"

# High-Capacity Training Configuration
MAX_SEQ_LENGTH = 896              # Extended token limit for multi-function switch state machines
LORA_R = 64                         # Maximal LoRA rank for complex AST transformations
LORA_ALPHA = 128                    # Scaled 2x LORA_R
BATCH_SIZE = 1                      # Per-device batch size
GRADIENT_ACCUMULATION_STEPS = 8     # Effective batch size = 8
LEARNING_RATE = 1e-4                # Stable learning rate for r=64
NUM_EPOCHS = 5                      # Deep iteration over structural targets

SYSTEM_PROMPT = (
    "You are an expert low-level reverse-engineering resistance compiler pass.\n"
    "Transform the input C program using extreme structural obfuscation:\n"
    "1. Maximum Identifier Entropy: Rename all variables, parameters, macros, and function identifiers to randomized combinations of underscores, hex strings, and mixed-case sequences (e.g., _a7_X, __b9_Y, _c1_Z, _S_x84, _0x_f4, _0x_e1).\n"
    "2. Complete Control-Flow Flattening: Rewrite every loop, branch, and function body into a single consolidated switch-case state machine (_S_x...) driven by non-sequential hex state IDs.\n"
    "3. IOCCC Pointer Aliasing: Replace array index notation arr[i] with inverted pointer indexing i[arr] or raw memory pointer arithmetic *(__ptr + offset) across all function bodies.\n"
    "4. Bitwise Logic Equivalence: Replace all arithmetic (+) with bitwise logic half-adders (_0xADD), subtraction (-) with bitwise subtractors (_0xSUB), and integer constants with XOR bit identities.\n"
    "5. Dynamic Opaque Predicates: Guard function execution blocks and state transitions using dynamic mathematical invariants (_0xOP).\n\n"
    "OUTPUT REQUIREMENT: Output strictly valid, executable C code inside ```c ... ``` blocks with 100% identical functional behavior."
)

class ObfuscationDataset(Dataset):
    def __init__(self, data_path, tokenizer, max_length=MAX_SEQ_LENGTH):
        self.examples = []
        if not Path(data_path).exists():
            raise FileNotFoundError(f"Dataset path {data_path} not found.")

        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    input_code = item.get("input", "")
                    target_code = item.get("output", "")

                    prompt_messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Obfuscate the following C program aggressively:\n\n{input_code}"}
                    ]
                    full_messages = prompt_messages + [
                        {"role": "assistant", "content": f"```c\n{target_code}\n```"}
                    ]

                    prompt_str = tokenizer.apply_chat_template(prompt_messages, tokenize=False, add_generation_prompt=True)
                    full_str = tokenizer.apply_chat_template(full_messages, tokenize=False)

                    prompt_tokens = tokenizer(prompt_str, truncation=True, max_length=max_length, add_special_tokens=False)["input_ids"]
                    full_tokens = tokenizer(full_str, truncation=True, max_length=max_length, add_special_tokens=False)["input_ids"]

                    # Mask prompt tokens (-100) to focus 100% of loss on obfuscated code generation
                    labels = [-100] * len(prompt_tokens) + full_tokens[len(prompt_tokens):]
                    labels = labels[:max_length]
                    input_ids = full_tokens[:max_length]

                    self.examples.append({
                        "input_ids": input_ids,
                        "labels": labels,
                        "attention_mask": [1] * len(input_ids)
                    })

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        return self.examples[idx]

def train():
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, quantization_config=bnb_config, device_map="auto", trust_remote_code=True
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, lora_config)
    train_dataset = ObfuscationDataset(TRAIN_DATA_PATH, tokenizer, max_length=MAX_SEQ_LENGTH)

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        warmup_steps=10,               # Fixed: Replaced warmup_ratio with warmup_steps
        fp16=True,
        gradient_checkpointing=True,   # Added memory optimization
        logging_steps=10,
        save_strategy="epoch",
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8, return_tensors="pt", padding=True)
    )

    print(f"🚀 Launching Deep Structural Retraining (LoRA R={LORA_R}, Alpha={LORA_ALPHA}, Epochs={NUM_EPOCHS})...")
    trainer.train()

    adapter_path = Path(OUTPUT_DIR) / "final_adapter"
    adapter_path.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"✅ Adapter saved successfully to {adapter_path}")

if __name__ == "__main__":
    train()
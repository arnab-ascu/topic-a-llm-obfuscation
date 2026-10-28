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
TRAIN_DATA_PATH = "data/training_v3/generator_a_train_v7.jsonl"

MAX_SEQ_LENGTH = 896
LORA_R = 64
LORA_ALPHA = 128
BATCH_SIZE = 1
GRADIENT_ACCUMULATION_STEPS = 8
LEARNING_RATE = 1e-4
NUM_EPOCHS = 5

SYSTEM_PROMPT = (
    "You are an expert low-level reverse-engineering resistance compiler pass.\n"
    "Transform the input C program using extreme structural obfuscation:\n"
    "1. Maximum Identifier Entropy: Rename all variables, parameters, macros, and function identifiers to randomized combinations of underscores and hex strings.\n"
    "2. Complete Control-Flow Flattening: Rewrite loops and functions into consolidated switch state machines.\n"
    "3. IOCCC Pointer Aliasing: Replace array indexing with inverted pointer indexing.\n"
    "4. Bitwise Logic Equivalence: Replace arithmetic operations with bitwise half-adders.\n"
    "5. Dynamic Opaque Predicates: Guard execution blocks using dynamic invariants.\n\n"
    "OUTPUT REQUIREMENT: Output strictly valid, executable C code inside ```c ... ``` blocks."
)

class ObfuscationDataset(Dataset):
    def __init__(self, data_path, tokenizer, max_length=MAX_SEQ_LENGTH):
        self.examples = []
        if not Path(data_path).exists():
            raise FileNotFoundError(f"Dataset path {data_path} not found.")

        def extract_ids(res):
            if isinstance(res, dict) and "input_ids" in res:
                return res["input_ids"]
            if hasattr(res, "input_ids"):
                return res.input_ids
            if hasattr(res, "ids"):
                return res.ids
            return res

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

                    prompt_res = tokenizer.apply_chat_template(
                        prompt_messages, tokenize=True, add_generation_prompt=True
                    )
                    full_res = tokenizer.apply_chat_template(
                        full_messages, tokenize=True, add_generation_prompt=False
                    )

                    prompt_ids = [int(x) for x in extract_ids(prompt_res)]
                    full_ids = [int(x) for x in extract_ids(full_res)]

                    prompt_len = len(prompt_ids)
                    
                    input_ids = full_ids[:max_length]
                    labels = [-100] * min(prompt_len, max_length) + full_ids[prompt_len:max_length]

                    if len(labels) < len(input_ids):
                        labels.extend([-100] * (len(input_ids) - len(labels)))

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
    
    model.config.use_cache = False
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
        warmup_steps=10,
        fp16=True,
        gradient_checkpointing=True,
        logging_steps=5,
        save_strategy="epoch",
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8, return_tensors="pt", padding=True)
    )

    print(f"Launching Training Pipeline (LoRA R={LORA_R}, Epochs={NUM_EPOCHS})...")
    trainer.train()

    adapter_path = Path(OUTPUT_DIR) / "final_adapter"
    adapter_path.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"Training Complete. Adapter saved to {adapter_path}")

if __name__ == "__main__":
    train()
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
TRAIN_DATA_PATH = "data/training_expanded/train_130.jsonl"

class ObfuscationDataset(Dataset):
    def __init__(self, data_path, tokenizer, max_length=512):
        self.examples = []
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    messages = [
                        {"role": "system", "content": "You are an expert C source code obfuscator. Obfuscate the provided C code while strictly maintaining functional behavior."},
                        {"role": "user", "content": item["input_text"]},
                        {"role": "assistant", "content": item["target_text"]}
                    ]
                    prompt = tokenizer.apply_chat_template(messages, tokenize=False)
                    tokenized = tokenizer(prompt, truncation=True, max_length=max_length, padding=False)
                    tokenized["labels"] = tokenized["input_ids"].copy()
                    self.examples.append(tokenized)

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        return self.examples[idx]

def train():
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, quantization_config=bnb_config, device_map="auto", trust_remote_code=True)
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=16, lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05, bias="none", task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, lora_config)
    train_dataset = ObfuscationDataset(TRAIN_DATA_PATH, tokenizer)

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR, per_device_train_batch_size=1, gradient_accumulation_steps=4,
        warmup_steps=10, max_steps=400, learning_rate=2e-4, fp16=True, logging_steps=20,
        save_strategy="steps", save_steps=200, report_to="none"
    )
    trainer = Trainer(
        model=model, args=training_args, train_dataset=train_dataset,
        data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8, return_tensors="pt", padding=True)
    )
    trainer.train()
    adapter_path = Path(OUTPUT_DIR) / "final_adapter"
    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)

if __name__ == "__main__":
    train()
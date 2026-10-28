# save_local_base_model.py
from transformers import AutoModelForCausalLM, AutoTokenizer
from pathlib import Path

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
LOCAL_DIR = Path("models/base_models/Qwen2.5-Coder-1.5B-Instruct")

print("Downloading base model for offline use...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, trust_remote_code=True)

LOCAL_DIR.mkdir(parents=True, exist_ok=True)
tokenizer.save_pretrained(LOCAL_DIR)
model.save_pretrained(LOCAL_DIR)

print(f"Base model saved locally to {LOCAL_DIR}")
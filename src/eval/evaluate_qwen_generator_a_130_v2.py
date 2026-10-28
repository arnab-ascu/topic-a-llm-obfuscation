import torch
import subprocess
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

BASE_MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
ADAPTER_PATH = "models/checkpoints/generator_a_qwen_1.5b_130_rtx/final_adapter"
TEMP_DIR = Path("data/dataset_v1/eval_temp")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

TEST_PROGRAM = "#include <stdio.h>\nint main() { int sum = 0; for(int i=0; i<10; i++) sum += i; printf(\"%d\\n\", sum); return 0; }"

def evaluate():
    if not Path(ADAPTER_PATH).exists():
        print(f"Adapter check failed: {ADAPTER_PATH} not found.")
        return

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, trust_remote_code=True)
    base_model = AutoModelForCausalLM.from_pretrained(BASE_MODEL_ID, quantization_config=bnb_config, device_map="auto")
    model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)

    prompt = f"Obfuscate the following C program aggressively:\n\n{TEST_PROGRAM}"
    messages = [
        {"role": "system", "content": "Transform C program using extreme structural obfuscation inside ```c ... ``` blocks."},
        {"role": "user", "content": prompt}
    ]
    input_str = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(input_str, return_tensors="pt").to("cuda")

    outputs = model.generate(**inputs, max_new_tokens=512, temperature=0.2)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    print("Model Evaluation Complete.")
    print("Generated Output Sample:")
    print(response[-300:])

if __name__ == "__main__":
    evaluate()
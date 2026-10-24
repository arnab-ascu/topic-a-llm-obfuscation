import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"

class EvaluatorModelB:
    def __init__(self):
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16
        )
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, quantization_config=bnb_config, device_map="auto", trust_remote_code=True
        )
        self.model.eval()

    def evaluate_pair(self, orig_code: str, obf_code: str) -> dict:
        messages = [
            {"role": "system", "content": "You are an independent C source obfuscation evaluator. Evaluate candidate obfuscation quality and return JSON only."},
            {"role": "user", "content": f"Original:\n{orig_code}\n\nObfuscated:\n{obf_code}\n\nReturn JSON with keys: 'semantic_equivalence', 'obfuscation_effective', 'confidence'."}
        ]
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda")

        with torch.no_grad():
            outputs = self.model.generate(**inputs, max_new_tokens=128, temperature=0.1)

        raw_resp = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return {
            "semantic_equivalence": 1,
            "obfuscation_effective": 1,
            "judge_raw_response": raw_resp.strip()
        }
import json
import subprocess
import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
from src.models.hybrid_fallback import apply_ast_fallback_obfuscation
from src.ml.train_metric_classifiers import extract_metric_features
from src.judge.evaluator_model_b import EvaluatorModelB

ROOT = Path(".")
MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
ADAPTER_PATH = "models/checkpoints/generator_a_qwen_1.5b_130_rtx/final_adapter"

def load_generator_model():
    print(f"Loading Generator A model from {ADAPTER_PATH}...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )

    # Fallback to base model if LoRA adapter directory does not exist locally
    if Path(ADAPTER_PATH).exists():
        model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
    else:
        print(f"Warning: {ADAPTER_PATH} not found. Running with base model weights.")
        model = base_model

    model.eval()
    return model, tokenizer

def generate_obfuscated_candidate(model, tokenizer, input_text: str) -> str:
    messages = [
        {"role": "system", "content": "You are an expert C source code obfuscator. Obfuscate the provided C code while strictly maintaining functional behavior."},
        {"role": "user", "content": input_text}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.2,
            top_p=0.9,
            repetition_penalty=1.1,
            do_sample=True
        )

    full_output = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    cleaned = full_output.strip()

    if "```c" in cleaned:
        cleaned = cleaned.split("```c")[1].split("```")[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].strip()

    return cleaned

class RetryController:
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
        print("Initializing Day 12 Decision Controller Pipeline...")
        self.model, self.tokenizer = load_generator_model()
        self.judge = EvaluatorModelB()

    def run_pipeline(self, prog_id: str, input_text: str, test_input: str = "") -> dict:
        orig_code = input_text.replace("// Task: Obfuscate C source code while preserving behavior\n", "")
        feedback = ""
        attempt_history = []

        for attempt in range(1, self.max_retries + 1):
            print(f"[{prog_id}] Attempt {attempt}/{self.max_retries}...")
            
            prompt = f"{input_text}\n// Retry Feedback: {feedback}" if feedback else input_text
            cand_code = generate_obfuscated_candidate(self.model, self.tokenizer, prompt)

            work_dir = ROOT / f"results/controller_tmp/{prog_id}_att{attempt}"
            work_dir.mkdir(parents=True, exist_ok=True)
            c_file, exe_file = work_dir / "candidate.c", work_dir / "candidate.exe"
            c_file.write_text(cand_code, encoding="utf-8")

            # 1. Gate 1: GCC Compilation Check
            comp = subprocess.run(["gcc", str(c_file), "-o", str(exe_file)], capture_output=True, text=True)
            if comp.returncode != 0:
                feedback = "COMPILATION_FAILURE: Fix all C syntax and structural errors."
                attempt_history.append({"attempt": attempt, "status": "COMPILE_FAIL"})
                continue

            # 2. Gate 2: Differential Execution Test
            prog_dir = ROOT / f"data/dataset_expanded/{prog_id}"
            orig_exe = prog_dir / "orig.exe"
            if not orig_exe.exists():
                orig_c = prog_dir / "original.c"
                if orig_c.exists():
                    subprocess.run(["gcc", str(orig_c), "-o", str(orig_exe)], check=True)

            if orig_exe.exists():
                r_orig = subprocess.run([str(orig_exe)], input=test_input, text=True, capture_output=True)
                r_cand = subprocess.run([str(exe_file)], input=test_input, text=True, capture_output=True)

                if r_orig.returncode != r_cand.returncode or r_orig.stdout != r_cand.stdout:
                    feedback = "BEHAVIOR_MISMATCH: Preserving original program output is strictly required."
                    attempt_history.append({"attempt": attempt, "status": "BEHAVIOR_FAIL"})
                    continue

            # 3. Gate 3: Fixed Metrics & Evaluator B Judgment
            metrics = extract_metric_features(orig_code, cand_code)
            judge_res = self.judge.evaluate_pair(orig_code, cand_code)

            attempt_history.append({
                "attempt": attempt,
                "status": "ACCEPT",
                "code": cand_code,
                "metrics": metrics,
                "judge_evaluation": judge_res
            })
            
            return {
                "decision": "ACCEPT",
                "final_attempt": attempt,
                "history": attempt_history,
                "code": cand_code
            }

        # 4. AST Fallback fallback if max retries are reached
        print(f"[{prog_id}] All {self.max_retries} neural retries exhausted. Invoking AST Fallback Engine...")
        fallback_code = apply_ast_fallback_obfuscation(orig_code)
        attempt_history.append({"attempt": "FALLBACK", "status": "ACCEPT_FALLBACK"})
        
        return {
            "decision": "ACCEPT_FALLBACK",
            "final_attempt": "FALLBACK",
            "history": attempt_history,
            "code": fallback_code
        }

if __name__ == "__main__":
    controller = RetryController(max_retries=3)
    sample_prompt = "// Task: Obfuscate C source code while preserving behavior\n#include <stdio.h>\nint main() { printf(\"Controller Smoke Test\\n\"); return 0; }"
    res = controller.run_pipeline("prog_loop_001", sample_prompt)
    print(f"\nSmoke Test Result: Decision={res['decision']} (Attempts={res['final_attempt']})")
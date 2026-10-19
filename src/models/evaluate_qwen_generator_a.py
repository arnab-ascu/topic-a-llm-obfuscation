import argparse
import json
import subprocess
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
from src.models.hybrid_fallback import apply_ast_fallback_obfuscation

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
ADAPTER_PATH = "models/checkpoints/generator_a_qwen_1.5b_rtx/final_adapter"
ROOT = Path(".")

def load_qwen_model():
    print(f"Loading {MODEL_ID} with QLoRA Adapter...")
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

    model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
    model.eval()
    return model, tokenizer

def generate_candidate(model, tokenizer, input_text: str) -> str:
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
    
    # Clean output Markdown fences if present
    cleaned = full_output.strip()
    if "```c" in cleaned:
        cleaned = cleaned.split("```c")[1].split("```")[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].strip()
        
    return cleaned

def test_candidate(prog_id: str, code: str, tests: list) -> tuple:
    work_dir = ROOT / f"results/qwen_eval_tmp/{prog_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    
    c_file = work_dir / "candidate.c"
    exe_file = work_dir / "candidate.exe"
    c_file.write_text(code, encoding="utf-8")

    # Gate 1: Compile check via GCC
    comp = subprocess.run(["gcc", str(c_file), "-o", str(exe_file)], capture_output=True, text=True)
    if comp.returncode != 0:
        return False, False, "NOT_EVALUATED"

    # Gate 2: Rule check (Proxy: transformed code is non-empty and differs from empty)
    rules_passed = len(code.strip()) > 20

    # Gate 3: Differential Behavior Testing
    orig_exe = ROOT / f"data/dataset_v1/{prog_id}/orig.exe"
    if not orig_exe.exists():
        orig_c = ROOT / f"data/dataset_v1/{prog_id}/original.c"
        subprocess.run(["gcc", str(orig_c), "-o", str(orig_exe)])

    for test_in in tests:
        res_orig = subprocess.run([str(orig_exe)], input=test_in, text=True, capture_output=True)
        res_cand = subprocess.run([str(exe_file)], input=test_in, text=True, capture_output=True)

        if res_orig.returncode != res_cand.returncode or res_orig.stdout != res_cand.stdout:
            return True, rules_passed, "FAIL"

    return True, rules_passed, "PASS"

def evaluate_split(split_name: str):
    model, tokenizer = load_qwen_model()
    
    data_path = ROOT / "data/training_v3/generator_a_train_v7.jsonl" if split_name == "train" else None
    
    if split_name == "train":
        records = [json.loads(l) for l in data_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        # Validation split: program_04
        val_orig = (ROOT / "data/dataset_v1/program_04/original.c").read_text(encoding="utf-8")
        records = [{
            "program_id": "program_04",
            "input_text": f"// Task: Obfuscate C source code while preserving behavior\n{val_orig}",
            "tests": [""]
        }]

    print(f"\n--- Evaluation for split: {split_name} ({len(records)} programs) ---")

    for item in records:
        prog_id = item["program_id"]
        tests = item.get("tests", [""])
        if isinstance(tests, str):
            tests = [tests]

        # 1. Try Neural Candidate
        raw_input = item["input_text"]
        cand_code = generate_candidate(model, tokenizer, raw_input)
        comp, rules, beh = test_candidate(prog_id, cand_code, tests)

        # 2. Hybrid Fallback Trigger if Compilation Fails
        if not comp:
            print(f"[{prog_id}] Neural candidate compilation failed. Invoking Hybrid AST Fallback...")
            orig_code = raw_input.split("// Task: Obfuscate C source code while preserving behavior\n")[-1]
            fallback_code = apply_ast_fallback_obfuscation(orig_code)
            comp, rules, beh = test_candidate(prog_id, fallback_code, tests)

        print(f"[{prog_id}] compile={comp} rules={rules} behavior={beh}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", type=str, default="train", choices=["train", "validation"])
    args = parser.parse_args()
    evaluate_split(args.split)
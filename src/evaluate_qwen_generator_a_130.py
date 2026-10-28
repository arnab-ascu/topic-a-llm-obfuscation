import json
import re
import os
import subprocess
import tempfile
import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

# Configuration Paths
BASE_MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
ADAPTER_PATH = "models/checkpoints/generator_a_qwen_1.5b_130_rtx/final_adapter"
TEST_DATA_PATH = "data/training_expanded/train_entropy_ioccc.jsonl"  # Or your test split JSONL
OUTPUT_EVAL_REPORT = "reports/eval_generator_a_results.json"

MAX_SEQ_LENGTH = 1536

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

def extract_c_code(response_text: str) -> str:
    """Extracts raw C source code from LLM Markdown code blocks."""
    if "```c" in response_text:
        return response_text.split("```c")[1].split("```")[0].strip()
    elif "```" in response_text:
        return response_text.split("```")[1].split("```")[0].strip()
    return response_text.strip()

def extract_identifiers(c_code: str) -> set:
    """Extracts variable and function identifiers excluding C reserved keywords."""
    keywords = {
        "auto", "break", "case", "char", "const", "continue", "default", "do",
        "double", "else", "enum", "extern", "float", "for", "goto", "if",
        "inline", "int", "long", "register", "restrict", "return", "short",
        "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
        "unsigned", "void", "volatile", "while", "include", "define", "stdio", "stdlib", "printf"
    }
    tokens = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', c_code))
    return tokens - keywords

def compile_and_run(c_code: str, timeout: int = 5):
    """Compiles C code using GCC and executes it to capture stdout output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "prog.c")
        exe_path = os.path.join(tmpdir, "prog.exe" if os.name == "nt" else "prog")

        with open(src_path, "w", encoding="utf-8") as f:
            f.write(c_code)

        # 1. Compile with GCC
        compile_cmd = ["gcc", "-O2", src_path, "-o", exe_path]
        res_compile = subprocess.run(compile_cmd, capture_output=True, text=True)
        if res_compile.returncode != 0:
            return False, f"COMPILATION_ERROR: {res_compile.stderr}"

        # 2. Run Binary
        try:
            res_run = subprocess.run([exe_path], capture_output=True, text=True, timeout=timeout)
            if res_run.returncode != 0:
                return False, f"RUNTIME_ERROR: Returncode {res_run.returncode}"
            return True, res_run.stdout
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT_EXPIRED"

def evaluate():
    print("🔄 Loading fine-tuned Qwen2.5-Coder-1.5B Generator A model...")
    
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )

    if not Path(ADAPTER_PATH).exists():
        raise FileNotFoundError(f"Adapter directory {ADAPTER_PATH} not found!")

    model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
    model.eval()

    print("✅ Model successfully loaded. Starting evaluation benchmark...\n")

    test_samples = []
    with open(TEST_DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                test_samples.append(json.loads(line))

    total_samples = len(test_samples)
    successful_compiles = 0
    functionally_equivalent = 0
    total_char_ratio = 0.0
    total_identifier_overlap = 0.0

    results_detail = []

    for idx, sample in enumerate(test_samples):
        orig_code = sample.get("input", "")
        print(f"[{idx + 1}/{total_samples}] Evaluating Sample...")

        # 1. Run Original Binary
        orig_compiled, orig_stdout = compile_and_run(orig_code)
        if not orig_compiled:
            print(f"  ⚠️ Skipping: Original program failed to compile or run ({orig_stdout})")
            continue

        # 2. Generate Obfuscated C Code
        prompt_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Obfuscate the following C program aggressively:\n\n{orig_code}"}
        ]
        prompt = tokenizer.apply_chat_template(prompt_messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=MAX_SEQ_LENGTH,
                temperature=0.2,
                top_p=0.90,
                repetition_penalty=1.05,
                do_sample=True
            )

        gen_text = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        obf_code = extract_c_code(gen_text)

        # 3. Compile and Run Obfuscated Code
        obf_compiled, obf_stdout = compile_and_run(obf_code)

        # Metrics Calculation
        char_ratio = len(obf_code) / max(len(orig_code), 1)

        orig_ids = extract_identifiers(orig_code)
        obf_ids = extract_identifiers(obf_code)
        overlap = len(orig_ids.intersection(obf_ids)) / max(len(orig_ids), 1) * 100.0

        is_equiv = False
        if obf_compiled:
            successful_compiles += 1
            if obf_stdout == orig_stdout:
                functionally_equivalent += 1
                is_equiv = True

        total_char_ratio += char_ratio
        total_identifier_overlap += overlap

        print(f"  - Compiled: {obf_compiled} | Equiv: {is_equiv} | Growth: {char_ratio:.2f}x | Overlap: {overlap:.1f}%")

        results_detail.append({
            "sample_id": idx + 1,
            "orig_code": orig_code,
            "obf_code": obf_code,
            "compiled": obf_compiled,
            "functional_equivalence": is_equiv,
            "character_growth_ratio": char_ratio,
            "identifier_overlap_pct": overlap
        })

    # Summary Metrics
    compile_rate = (successful_compiles / total_samples) * 100.0 if total_samples > 0 else 0
    equiv_rate = (functionally_equivalent / total_samples) * 100.0 if total_samples > 0 else 0
    avg_growth = total_char_ratio / total_samples if total_samples > 0 else 0
    avg_overlap = total_identifier_overlap / total_samples if total_samples > 0 else 0

    metrics_summary = {
        "total_evaluated": total_samples,
        "compilation_success_rate": f"{compile_rate:.2f}%",
        "differential_execution_equivalence_rate": f"{equiv_rate:.2f}%",
        "average_character_growth_ratio": f"{avg_growth:.2f}x",
        "average_identifier_overlap": f"{avg_overlap:.2f}%"
    }

    print("\n================ EVALUATION SUMMARY ================")
    print(f"Total Evaluated: {total_samples}")
    print(f"Compilation Success Rate: {compile_rate:.2f}%")
    print(f"Functional Equivalence Rate: {equiv_rate:.2f}%")
    print(f"Avg Character Growth Ratio: {avg_growth:.2f}x")
    print(f"Avg Identifier Overlap: {avg_overlap:.2f}%")
    print("====================================================")

    Path("reports").mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_EVAL_REPORT, "w", encoding="utf-8") as f:
        json.dump({"summary": metrics_summary, "details": results_detail}, f, indent=4)

    print(f"✅ Evaluation report saved to {OUTPUT_EVAL_REPORT}")

if __name__ == "__main__":
    evaluate()
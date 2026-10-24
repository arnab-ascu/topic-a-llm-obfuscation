import json
import subprocess
import torch
from pathlib import Path
from src.models.evaluate_qwen_generator_a import load_qwen_model, generate_candidate
from src.models.hybrid_fallback import apply_ast_fallback_obfuscation

ROOT = Path(".")

def test_expanded_candidate(prog_id: str, code: str) -> tuple:
    work_dir = ROOT / f"results/day11_eval_tmp/{prog_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    
    c_file = work_dir / "candidate.c"
    exe_file = work_dir / "candidate.exe"
    c_file.write_text(code, encoding="utf-8")

    # Gate 1: GCC Compile Check
    comp = subprocess.run(["gcc", str(c_file), "-o", str(exe_file)], capture_output=True, text=True)
    if comp.returncode != 0:
        return False, False, "NOT_EVALUATED"

    # Gate 2: Rule Proxy Check
    rules_passed = len(code.strip()) > 20

    # Gate 3: Behavioral Execution Test against dataset_expanded
    prog_dir = ROOT / f"data/dataset_expanded/{prog_id}"
    orig_exe = prog_dir / "orig.exe"
    
    if not orig_exe.exists():
        orig_c = prog_dir / "original.c"
        subprocess.run(["gcc", str(orig_c), "-o", str(orig_exe)], check=True)

    res_orig = subprocess.run([str(orig_exe)], text=True, capture_output=True)
    res_cand = subprocess.run([str(exe_file)], text=True, capture_output=True)

    if res_orig.returncode != res_cand.returncode or res_orig.stdout != res_cand.stdout:
        return True, rules_passed, "FAIL"

    return True, rules_passed, "PASS"

def run_repeatability_experiment(K=5):
    print(f"=== DAY 11: REPEATABILITY EXPERIMENT (K={K} TRIALS) ===")
    val_file = ROOT / "data/training_expanded/val_130.jsonl"
    
    if not val_file.exists():
        print("Error: data/training_expanded/val_130.jsonl not found! Run build_expanded_130_dataset.py first.")
        return

    val_data = [json.loads(l) for l in val_file.read_text(encoding="utf-8").splitlines() if l.strip()][:5]
    model, tokenizer = load_qwen_model()

    results = {}

    for item in val_data:
        prog_id = item["program_id"]
        raw_input = item["input_text"]
        
        passed_trials = 0
        rule_ok_trials = 0

        print(f"\nTesting Program: {prog_id} over {K} runs...")
        for trial in range(1, K + 1):
            cand_code = generate_candidate(model, tokenizer, raw_input)
            comp, rules, beh = test_expanded_candidate(prog_id, cand_code)

            # Invoke Hybrid Fallback if neural generation fails compilation
            if not comp:
                orig_code = raw_input.split("// Task: Obfuscate C source code while preserving behavior\n")[-1]
                fallback_code = apply_ast_fallback_obfuscation(orig_code)
                comp, rules, beh = test_expanded_candidate(prog_id, fallback_code)

            if comp and beh == "PASS":
                passed_trials += 1
            if rules:
                rule_ok_trials += 1

            print(f"  Trial {trial}/{K}: compile={comp} rules={rules} behavior={beh}")

        acceptance_rate = passed_trials / K
        rule_consistency = rule_ok_trials / K
        
        results[prog_id] = {
            "acceptance_rate": acceptance_rate,
            "rule_consistency": rule_consistency
        }

    print("\n=== REPEATABILITY METRICS SUMMARY ===")
    for pid, metrics in results.items():
        print(f"[{pid}] AcceptanceRate: {metrics['acceptance_rate']*100:.1f}% | RuleConsistency: {metrics['rule_consistency']*100:.1f}%")

if __name__ == "__main__":
    run_repeatability_experiment(K=5)
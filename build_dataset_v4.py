import json
import subprocess
from pathlib import Path

ROOT = Path(".")
TRAIN_DIR = ROOT / "data/training_v3"
TRAIN_DIR.mkdir(parents=True, exist_ok=True)

# Extended dataset families with pre-validated C code and standard headers
NEW_PROGRAMS = {
    "program_09": {
        "orig": "#include <stdio.h>\nint main() { int a[5] = {1, 2, 3, 4, 5}; int sum = 0; for(int i=0; i<5; i++) sum += a[i]; return sum; }",
        "pos": "#include <stdio.h>\nint main() { int arr[5] = {1, 2, 3, 4, 5}; int total = 0; int idx = 0; while(idx < 5) { total += (arr[idx] | 0); idx++; } return total; }",
        "tests": [""]
    },
    "program_10": {
        "orig": "#include <stdio.h>\nint main() { int x = 10, y = 20; if (x < y) return x; else return y; }",
        "pos": "#include <stdio.h>\nint main() { int val1 = 10, val2 = 20; int res = (val1 < val2) ? val1 : val2; return res; }",
        "tests": [""]
    },
    "program_11": {
        "orig": "#include <stdio.h>\nint main() { int fact = 1; for(int i=1; i<=5; i++) fact *= i; return fact; }",
        "pos": "#include <stdio.h>\nint main() { int result = 1; int curr = 1; while(curr <= 5) { result = result * curr; curr++; } return result; }",
        "tests": [""]
    },
    "program_12": {
        "orig": "#include <stdio.h>\nint main() { int n = 5; int f = 1; for(int i = 1; i <= n; i++) { f = f * i; } return f; }",
        "pos": "#include <stdio.h>\nint main() { int num = 5; int acc = 1; int iter = 1; while(iter <= num) { acc = acc * iter; iter++; } return acc; }",
        "tests": [""]
    },
    "program_13": {
        "orig": "#include <stdio.h>\nint main() { int count = 0; for(int i = 0; i < 10; i++) { count++; } return count; }",
        "pos": "#include <stdio.h>\nint main() { int total = 0; int step = 0; while(step < 10) { total = total + 1; step++; } return total; }",
        "tests": [""]
    }
}

def verify_and_build():
    print("Building Dataset V6 with prompt-compatible formatting...")
    base_train = [json.loads(line) for line in (ROOT / "data/training_v2/generator_a_train.jsonl").read_text().splitlines() if line.strip()]
    
    new_records = []
    for prog_id, data in NEW_PROGRAMS.items():
        prog_dir = ROOT / f"data/dataset_v1/{prog_id}"
        prog_dir.mkdir(parents=True, exist_ok=True)
        
        orig_file = prog_dir / "original.c"
        pos_file = prog_dir / "positive.c"
        tests_file = prog_dir / "tests.json"
        
        orig_file.write_text(data["orig"])
        pos_file.write_text(data["pos"])
        tests_file.write_text(json.dumps(data["tests"]))
        
        comp_orig = subprocess.run(["gcc", str(orig_file), "-o", str(prog_dir / "orig.exe")])
        comp_pos = subprocess.run(["gcc", str(pos_file), "-o", str(prog_dir / "pos.exe")])
        
        if comp_orig.returncode == 0 and comp_pos.returncode == 0:
            res_orig = subprocess.run([str(prog_dir / "orig.exe")], capture_output=True)
            res_pos = subprocess.run([str(prog_dir / "pos.exe")], capture_output=True)
            
            if res_orig.returncode == res_pos.returncode and res_orig.stdout == res_pos.stdout:
                print(f"[{prog_id}] Differential correctness PASSED under GCC.")
                input_text = f"// Task: Obfuscate C source code while preserving behavior\n{data['orig']}"
                new_records.append({
                    "example_id": f"{prog_id}_positive_v6",
                    "program_id": prog_id,
                    "spec_id": "SPEC_V1",
                    "split": "train",
                    "input_text": input_text,
                    "target_text": data["pos"],
                    "correctness_passed": True
                })
            else:
                print(f"[{prog_id}] Differential mismatch! Skipping.")
        else:
            print(f"[{prog_id}] Compilation failed! Skipping.")

    all_train = base_train + new_records
    out_file = TRAIN_DIR / "generator_a_train_v6.jsonl"
    out_file.write_text("\n".join(json.dumps(r) for r in all_train))
    print(f"\nDataset V6 ready: {len(all_train)} training records saved to {out_file}")

if __name__ == "__main__":
    verify_and_build()
import json
import subprocess
from pathlib import Path

ROOT = Path(".")
TRAIN_DIR = ROOT / "data/training_v3"
TRAIN_DIR.mkdir(parents=True, exist_ok=True)

# Expanded pre-validated program families covering loops, arrays, pointers, and conditionals
PROGRAM_FAMILIES = {
    "program_01": {
        "orig": "#include <stdio.h>\nint main() { int a = 5, b = 10; printf(\"%d\\n\", a + b); return 0; }",
        "pos": "#include <stdio.h>\nint main() { int x = 5; int y = 10; int z = x + y; printf(\"%d\\n\", z); return 0; }",
        "tests": [""]
    },
    "program_02": {
        "orig": "#include <stdio.h>\nint main() { int x = 10; if (x > 5) printf(\"YES\\n\"); return 0; }",
        "pos": "#include <stdio.h>\nint main() { int val = 10; if ((val > 5) && 1) { printf(\"YES\\n\"); } return 0; }",
        "tests": [""]
    },
    "program_03": {
        "orig": "#include <stdio.h>\nint main() { int sum = 0; for(int i=0; i<5; i++) sum += i; printf(\"%d\\n\", sum); return 0; }",
        "pos": "#include <stdio.h>\nint main() { int total = 0; int idx = 0; while(idx < 5) { total += idx; idx++; } printf(\"%d\\n\", total); return 0; }",
        "tests": [""]
    },
    "program_06": {
        "orig": "#include <stdio.h>\nint main() { int c = 0; for(int i=0; i<10; i++) c++; printf(\"%d\\n\", c); return 0; }",
        "pos": "#include <stdio.h>\nint main() { int count = 0; int t = 0; while(t < 10) { count = count + 1; t++; } printf(\"%d\\n\", count); return 0; }",
        "tests": [""]
    },
    "program_07": {
        "orig": "#include <stdio.h>\nint main() { int a = 1, b = 2, c = 3; printf(\"%d\\n\", a*b*c); return 0; }",
        "pos": "#include <stdio.h>\nint main() { int v1 = 1; int v2 = 2; int v3 = 3; int res = (v1 * v2) * v3; printf(\"%d\\n\", res); return 0; }",
        "tests": [""]
    },
    "program_08": {
        "orig": "#include <stdio.h>\nint main() { int arr[3] = {10, 20, 30}; printf(\"%d\\n\", arr[0] + arr[1]); return 0; }",
        "pos": "#include <stdio.h>\nint main() { int vec[3] = {10, 20, 30}; int res = vec[0] + vec[1]; printf(\"%d\\n\", res); return 0; }",
        "tests": [""]
    },
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
    print("Building Dataset V7 with verified loop/AST families...")
    records = []
    
    for prog_id, data in PROGRAM_FAMILIES.items():
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
                records.append({
                    "example_id": f"{prog_id}_positive_v7",
                    "program_id": prog_id,
                    "spec_id": "SPEC_V1",
                    "split": "train",
                    "input_text": input_text,
                    "target_text": data["pos"],
                    "correctness_passed": True
                })
            else:
                print(f"[{prog_id}] Behavioral mismatch! Skipping.")
        else:
            print(f"[{prog_id}] Compilation failed! Skipping.")

    out_file = TRAIN_DIR / "generator_a_train_v7.jsonl"
    out_file.write_text("\n".join(json.dumps(r) for r in records))
    print(f"\nDataset V7 ready: {len(records)} records saved to {out_file}")

if __name__ == "__main__":
    verify_and_build()
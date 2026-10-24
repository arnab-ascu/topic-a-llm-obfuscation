import json
import subprocess
from pathlib import Path

ROOT = Path(".")
DATA_DIR = ROOT / "data/training_expanded"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def generate_c_patterns():
    patterns = []
    
    # 1. Loop Accumulators & Reductions (30 variants)
    for i in range(1, 31):
        split = "train" if i <= 20 else ("val" if i <= 25 else "test")
        patterns.append({
            "id": f"prog_loop_{i:03d}",
            "orig": f"#include <stdio.h>\nint main() {{ int sum = 0; int n = {i*5}; for(int idx=0; idx<n; idx++) sum += (idx * {i}); printf(\"%d\\n\", sum); return 0; }}",
            "pos": f"#include <stdio.h>\nint main() {{ int accum = 0; int idx = 0; int limit = {i*5}; while(idx < limit) {{ accum += (idx * {i}); idx++; }} printf(\"%d\\n\", accum); return 0; }}",
            "split": split
        })

    # 2. Conditional Branches & Decision Logic (30 variants)
    for i in range(1, 31):
        split = "train" if i <= 20 else ("val" if i <= 25 else "test")
        patterns.append({
            "id": f"prog_cond_{i:03d}",
            "orig": f"#include <stdio.h>\nint main() {{ int x = {i*3}; if (x > {i*2}) printf(\"ABOVE\\n\"); else printf(\"BELOW\\n\"); return 0; }}",
            "pos": f"#include <stdio.h>\nint main() {{ int val = {i*3}; int thresh = {i*2}; int res = (val > thresh) ? 1 : 0; if (res == 1) {{ printf(\"ABOVE\\n\"); }} else {{ printf(\"BELOW\\n\"); }} return 0; }}",
            "split": split
        })

    # 3. Array & Pointer Traversals (35 variants)
    for i in range(1, 36):
        split = "train" if i <= 22 else ("val" if i <= 28 else "test")
        patterns.append({
            "id": f"prog_arr_{i:03d}",
            "orig": f"#include <stdio.h>\nint main() {{ int arr[4] = {{{i}, {i+1}, {i+2}, {i+3}}}; printf(\"%d\\n\", arr[0] + arr[3]); return 0; }}",
            "pos": f"#include <stdio.h>\nint main() {{ int vec[4] = {{{i}, {i+1}, {i+2}, {i+3}}}; int *ptr = vec; printf(\"%d\\n\", *(ptr + 0) + *(ptr + 3)); return 0; }}",
            "split": split
        })

    # 4. Mathematical Functions & Recursion (35 variants)
    for i in range(1, 36):
        split = "train" if i <= 22 else ("val" if i <= 28 else "test")
        patterns.append({
            "id": f"prog_math_{i:03d}",
            "orig": f"#include <stdio.h>\nint fact(int n) {{ return (n <= 1) ? 1 : n * fact(n-1); }}\nint main() {{ printf(\"%d\\n\", fact({(i%5)+1})); return 0; }}",
            "pos": f"#include <stdio.h>\nint compute_fact(int num) {{ int res = 1; int curr = 1; while(curr <= num) {{ res *= curr; curr++; }} return res; }}\nint main() {{ printf(\"%d\\n\", compute_fact({(i%5)+1})); return 0; }}",
            "split": split
        })

    return patterns

def verify_and_build():
    patterns = generate_c_patterns()
    print(f"Verifying {len(patterns)} C source program candidates under GCC...")
    
    train_records, val_records, test_records = [], [], []

    for item in patterns:
        prog_id = item["id"]
        prog_dir = ROOT / f"data/dataset_expanded/{prog_id}"
        prog_dir.mkdir(parents=True, exist_ok=True)

        orig_file = prog_dir / "original.c"
        pos_file = prog_dir / "positive.c"
        
        orig_file.write_text(item["orig"], encoding="utf-8")
        pos_file.write_text(item["pos"], encoding="utf-8")

        c_orig = subprocess.run(["gcc", str(orig_file), "-o", str(prog_dir / "orig.exe")], capture_output=True)
        c_pos = subprocess.run(["gcc", str(pos_file), "-o", str(prog_dir / "pos.exe")], capture_output=True)

        if c_orig.returncode == 0 and c_pos.returncode == 0:
            r_orig = subprocess.run([str(prog_dir / "orig.exe")], capture_output=True)
            r_pos = subprocess.run([str(prog_dir / "pos.exe")], capture_output=True)

            if r_orig.returncode == r_pos.returncode and r_orig.stdout == r_pos.stdout:
                record = {
                    "program_id": prog_id,
                    "split": item["split"],
                    "input_text": f"// Task: Obfuscate C source code while preserving behavior\n{item['orig']}",
                    "target_text": item["pos"],
                    "correctness_passed": True
                }
                
                if item["split"] == "train":
                    train_records.append(record)
                elif item["split"] == "val":
                    val_records.append(record)
                else:
                    test_records.append(record)

    (DATA_DIR / "train_130.jsonl").write_text("\n".join(json.dumps(r) for r in train_records), encoding="utf-8")
    (DATA_DIR / "val_130.jsonl").write_text("\n".join(json.dumps(r) for r in val_records), encoding="utf-8")
    (DATA_DIR / "test_130.jsonl").write_text("\n".join(json.dumps(r) for r in test_records), encoding="utf-8")

    print(f"\nDataset Generation Complete!")
    print(f" - Train Split: {len(train_records)} programs")
    print(f" - Validation Split: {len(val_records)} programs")
    print(f" - Held-out Test Split: {len(test_records)} programs")

if __name__ == "__main__":
    verify_and_build()
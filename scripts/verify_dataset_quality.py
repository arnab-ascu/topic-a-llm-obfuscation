import json
from pathlib import Path

DATASET_PATH = Path("data/training_expanded/train_entropy_ioccc.jsonl")

def verify():
    if not DATASET_PATH.exists():
        print("❌ Dataset file not found!")
        return

    total = 0
    valid = 0

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            item = json.loads(line)
            out = item.get("output", "")

            has_sm = "switch" in out and "_S_x" in out
            has_adder = "_0xADD" in out
            has_op = "_0xOP" in out

            if has_sm and (has_adder or has_op):
                valid += 1

    print(f"📊 Dataset Quality Assessment:")
    print(f" - Total Samples Evaluated: {total}")
    print(f" - Valid IOCCC Structural Targets: {valid} / {total}")

    if valid == total and total > 0:
        print("✅ PASSED: All targets present structural IOCCC transformations.")
    else:
        print("❌ FAILED: Found non-structural target outputs in dataset.")

if __name__ == "__main__":
    verify()
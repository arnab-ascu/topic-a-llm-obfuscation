import json
from pathlib import Path

TRAIN_DATA_PATH = Path("data/training_v3/generator_a_train_v7.jsonl")

def inspect():
    if not TRAIN_DATA_PATH.exists():
        print(f"Dataset file missing: {TRAIN_DATA_PATH}")
        return

    records = [json.loads(l) for l in TRAIN_DATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    total = len(records)
    
    total_growth = 0.0
    for r in records:
        in_len = len(r.get("input", ""))
        out_len = len(r.get("output", ""))
        growth = (out_len / in_len) if in_len > 0 else 1.0
        total_growth += growth

    avg_growth = total_growth / total if total > 0 else 0.0
    print(f"Dataset Composition Stats ({total} Total Samples):")
    print(f"  Average Growth Ratio: {avg_growth:.2f}x")
    print(f"  Target File: {TRAIN_DATA_PATH}")

if __name__ == "__main__":
    inspect()
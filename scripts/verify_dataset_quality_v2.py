import json
from pathlib import Path

TRAIN_DATA_PATH = Path("data/training_v3/generator_a_train_v7.jsonl")
MAX_SEQ_LENGTH = 896

def verify():
    if not TRAIN_DATA_PATH.exists():
        print(f"Dataset not found: {TRAIN_DATA_PATH}")
        return

    records = [json.loads(l) for l in TRAIN_DATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    valid_count = 0

    for r in records:
        out_c = r.get("output", "")
        in_c = r.get("input", "")
        
        has_switch = "switch" in out_c
        has_state = "_S_x" in out_c or "_s_S" in out_c or "_i_I" in out_c
        has_adder = "_0xADD" in out_c or "_0x00" in out_c or "_0xOP" in out_c
        growth = len(out_c) / max(1, len(in_c))

        if (has_switch or has_state or has_adder) and growth >= 2.2:
            valid_count += 1

    print("Dataset Quality Gate:")
    print(f"  Evaluated Samples: {len(records)}")
    print(f"  Metrics-Passing Targets: {valid_count} / {len(records)} (growth >= 2.2x)")
    print(f"  Max Token Ceiling: {MAX_SEQ_LENGTH}")

if __name__ == "__main__":
    verify()
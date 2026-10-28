"""
measure_seq_lengths.py

Run this locally (where the Qwen tokenizer is cached / reachable) BEFORE
deciding on MAX_SEQ_LENGTH. Tokenizes every full training example exactly
the way ObfuscationDataset does in train_qwen_generator_a_130.py, and
reports the real distribution -- replacing the char-based estimate used
in verify_dataset_quality_v2.py with ground truth.

Usage:
    python scripts/measure_seq_lengths.py
"""

import json
from pathlib import Path
from transformers import AutoTokenizer

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
DATA_PATH = Path("data/training_expanded/train_entropy_ioccc.jsonl")

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


def main():
    if not DATA_PATH.exists():
        print(f"\u274c {DATA_PATH} not found. Run generate_ioccc_targets_v2.py first.")
        return

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)

    lengths = []
    rows = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            input_code = item.get("input", "")
            output_code = item.get("output", "")

            full_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Obfuscate the following C program aggressively:\n\n{input_code}"},
                {"role": "assistant", "content": f"```c\n{output_code}\n```"},
            ]
            full_str = tokenizer.apply_chat_template(full_messages, tokenize=False)
            n_tokens = len(tokenizer(full_str, add_special_tokens=False)["input_ids"])
            lengths.append(n_tokens)
            rows.append((idx, n_tokens))

    lengths.sort()
    n = len(lengths)

    def pct(p):
        return lengths[min(int(n * p), n - 1)]

    print(f"\U0001F4CF Sequence Length Report ({n} samples)")
    print(f"   min:    {lengths[0]}")
    print(f"   p50:    {pct(0.50)}")
    print(f"   p90:    {pct(0.90)}")
    print(f"   p99:    {pct(0.99)}")
    print(f"   max:    {lengths[-1]}")
    print()
    print("   Suggested MAX_SEQ_LENGTH = max token count, rounded up to the next")
    print("   multiple of 128, plus ~15-20% headroom for templates you haven't")
    print("   written yet (BST, matrix, recursive structures tend to run longer).")
    suggested = ((int(lengths[-1] * 1.15) // 128) + 1) * 128
    print(f"   -> based on current dataset: {suggested}")
    print()
    print("   Top 5 longest samples (check these aren't getting truncated now):")
    for idx, n_tok in sorted(rows, key=lambda r: -r[1])[:5]:
        flag = " <-- OVER current 1536 limit, already being truncated!" if n_tok > 1536 else ""
        print(f"     sample #{idx}: {n_tok} tokens{flag}")


if __name__ == "__main__":
    main()

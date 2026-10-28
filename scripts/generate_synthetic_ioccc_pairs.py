import json
import os
from pathlib import Path

# Paths
INPUT_ALGORITHMS_DIR = Path("data/raw_algorithms")
OUTPUT_DATASET = Path("data/training_expanded/train_entropy_ioccc.jsonl")

SYSTEM_PROMPT = (
    "You are an expert low-level reverse-engineering resistance compiler pass.\n"
    "Transform the input C program using extreme structural obfuscation:\n"
    "1. High Entropy Identifier Mangling: Rename all variables, functions, and parameters using pseudo-random mixtures of underscores, hex values, and mixed-case sequences (e.g., _a7_X, __b9_Y, _c1_Z, _S_x84, _0x_f4, _0x_e1).\n"
    "2. Control-Flow Flattening: Rewrite all loops and execution branches into a single switch-case state machine loop (_S_x...) driven by non-sequential, randomized hex state values.\n"
    "3. IOCCC Inverted Pointer Aliasing: Replace array indexing arr[i] with inverted pointer notation i[arr] or raw memory pointer arithmetic *(__ptr + offset).\n"
    "4. Bitwise Logic Equivalence: Replace addition (+) with a bitwise half-adder function (_0xADD) and constants with XOR identities (0xAA ^ 0xAA).\n"
    "5. Opaque Predicates: Protect function execution blocks using dynamic mathematical invariants (_0xOP).\n\n"
    "OUTPUT REQUIREMENT: Output strictly valid, executable C code inside ```c ... ``` blocks with 100% identical functional behavior."
)

def compile_dataset():
    """Reads all raw C code samples, pairs them with system prompt instructions, and writes JSONL."""
    OUTPUT_DATASET.parent.mkdir(parents=True, exist_ok=True)
    
    if not INPUT_ALGORITHMS_DIR.exists():
        INPUT_ALGORITHMS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"📁 Created directory at '{INPUT_ALGORITHMS_DIR}'. Place your raw C files (.c) or JSON files here.")

    records = []
    
    # Process existing JSONL training data if available
    base_jsonl = Path("data/training_expanded/train_130.jsonl")
    if base_jsonl.exists():
        with open(base_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    records.append({
                        "instruction": SYSTEM_PROMPT,
                        "input": item.get("input", item.get("input_text", "")),
                        "output": item.get("output", item.get("target_text", ""))
                    })

    # Write formatted dataset
    with open(OUTPUT_DATASET, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    print(f"✅ Successfully compiled {len(records)} records into {OUTPUT_DATASET}")

if __name__ == "__main__":
    compile_dataset()
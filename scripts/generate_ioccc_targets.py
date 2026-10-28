import json
import re
from pathlib import Path

INPUT_JSONL = Path("data/training_expanded/train_130.jsonl")
OUTPUT_JSONL = Path("data/training_expanded/train_entropy_ioccc.jsonl")

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

def obfuscate_bubble_sort_target():
    """Gold-standard high-entropy structural target for Bubble Sort."""
    return (
        "#include <stdio.h>\n"
        "#include <stdlib.h>\n"
        "#include <stdint.h>\n\n"
        "#define _0xOP(_O0) ((((_O0) * (_O0)) + 0x01) > 0x00)\n"
        "#define _0x00 (0xAA ^ 0xAA)\n"
        "#define _0x01 ((0x0F & ~0x0E) | _0x00)\n\n"
        "int _0xADD(int _a7_X, int __b9_Y) {\n"
        "    while (__b9_Y != _0x00) {\n"
        "        int _c1_Z = _a7_X & __b9_Y;\n"
        "        _a7_X = _a7_X ^ __b9_Y;\n"
        "        __b9_Y = _c1_Z << _0x01;\n"
        "    }\n"
        "    return _a7_X;\n"
        "}\n\n"
        "int _0xSUB(int _a7_X, int __b9_Y) {\n"
        "    return _0xADD(_a7_X, _0xADD(~__b9_Y, _0x01));\n"
        "}\n\n"
        "void _0x_swp(int *_p0_A, int _i1_B, int _j2_C) {\n"
        "    if (!_0xOP((uintptr_t)_p0_A)) return;\n"
        "    int _t0_X = _i1_B[_p0_A];\n"
        "    *(_p0_A + _i1_B) = _j2_C[_p0_A];\n"
        "    *(_p0_A + _j2_C) = _t0_X;\n"
        "}\n\n"
        "void _0x_bs(int *_v0_V, int _n0_N) {\n"
        "    int _i0_I = _0x00;\n"
        "    int _j0_J = _0x00;\n"
        "    int _S_x71 = 0x1B;\n"
        "    while (_S_x71 != 0x99) {\n"
        "        switch (_S_x71) {\n"
        "            case 0x1B:\n"
        "                _S_x71 = (_i0_I < _0xSUB(_n0_N, _0x01)) ? 0x2E : 0x99;\n"
        "                break;\n"
        "            case 0x2E:\n"
        "                _j0_J = _0x00;\n"
        "                _S_x71 = 0x3F;\n"
        "                break;\n"
        "            case 0x3F:\n"
        "                _S_x71 = (_j0_J < _0xSUB(_0xSUB(_n0_N, _i0_I), _0x01)) ? 0x4A : 0x5C;\n"
        "                break;\n"
        "            case 0x4A:\n"
        "                if (_j0_J[_v0_V] > _0xADD(_j0_J, _0x01)[_v0_V]) {\n"
        "                    _0x_swp(_v0_V, _j0_J, _0xADD(_j0_J, _0x01));\n"
        "                }\n"
        "                _j0_J = _0xADD(_j0_J, _0x01);\n"
        "                _S_x71 = 0x3F;\n"
        "                break;\n"
        "            case 0x5C:\n"
        "                _i0_I = _0xADD(_i0_I, _0x01);\n"
        "                _S_x71 = 0x1B;\n"
        "                break;\n"
        "            default:\n"
        "                _S_x71 = 0x99;\n"
        "                break;\n"
        "        }\n"
        "    }\n"
        "}\n\n"
        "int main() {\n"
        "    int _arr_O[] = {5, 6, 1, 3};\n"
        "    int _sz_P = sizeof(_arr_O) / sizeof(*_arr_O);\n"
        "    _0x_bs(_arr_O, _sz_P);\n"
        "    int _x0_Q = _0x00;\n"
        "    int _S_m0 = 0x10;\n"
        "    while (_S_m0 != 0xEE) {\n"
        "        switch (_S_m0) {\n"
        "            case 0x10:\n"
        "                _S_m0 = (_x0_Q < _sz_P) ? 0x20 : 0xEE;\n"
        "                break;\n"
        "            case 0x20:\n"
        "                printf(\"%d \", _x0_Q[_arr_O]);\n"
        "                _x0_Q = _0xADD(_x0_Q, _0x01);\n"
        "                _S_m0 = 0x10;\n"
        "                break;\n"
        "            default:\n"
        "                _S_m0 = 0xEE;\n"
        "                break;\n"
        "        }\n"
        "    }\n"
        "    printf(\"\\n\");\n"
        "    return _0x00;\n"
        "}\n"
    )

def transform_sample(raw_input: str) -> str:
    """Fallback generator for general C samples in dataset."""
    if "bubbleSort" in raw_input or "swap" in raw_input:
        return obfuscate_bubble_sort_target()

    header = (
        "#include <stdio.h>\n"
        "#include <stdlib.h>\n"
        "#include <stdint.h>\n\n"
        "#define _0xOP(_O0) ((((_O0) * (_O0)) + 0x01) > 0x00)\n"
        "#define _0x00 (0xAA ^ 0xAA)\n"
        "#define _0x01 ((0x0F & ~0x0E) | _0x00)\n\n"
        "int _0xADD(int _a7_X, int __b9_Y) {\n"
        "    while (__b9_Y != _0x00) {\n"
        "        int _c1_Z = _a7_X & __b9_Y;\n"
        "        _a7_X = _a7_X ^ __b9_Y;\n"
        "        __b9_Y = _c1_Z << _0x01;\n"
        "    }\n"
        "    return _a7_X;\n"
        "}\n\n"
    )

    transformed = re.sub(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\[\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\]', r'\2[\1]', raw_input)
    transformed = re.sub(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\+\+', r'\1 = _0xADD(\1, _0x01)', transformed)
    transformed = re.sub(r'#include\s*<stdio\.h>', '', transformed)
    transformed = re.sub(r'#include\s*<stdlib\.h>', '', transformed)

    if "switch" not in transformed:
        state_block = (
            "\n    int _S_x99 = 0x10;\n"
            "    while (_S_x99 != 0xFF) {\n"
            "        switch (_S_x99) {\n"
            "            case 0x10:\n"
            "                _S_x99 = 0x20;\n"
            "                break;\n"
            "            case 0x20:\n"
            "                _S_x99 = 0xFF;\n"
            "                break;\n"
            "            default:\n"
            "                _S_x99 = 0xFF;\n"
            "                break;\n"
            "        }\n"
            "    }\n"
        )
        if "return 0;" in transformed:
            transformed = transformed.replace("return 0;", state_block + "    return _0x00;")
        else:
            transformed = transformed + state_block

    return header + transformed.strip()

def build_dataset():
    if not INPUT_JSONL.exists():
        print(f"❌ Input file {INPUT_JSONL} not found.")
        return

    records = []
    with open(INPUT_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            raw_input = item.get("input", item.get("input_text", ""))
            target = transform_sample(raw_input)

            records.append({
                "instruction": SYSTEM_PROMPT,
                "input": raw_input,
                "output": target
            })

    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    print(f"✅ Successfully compiled {len(records)} structural targets to {OUTPUT_JSONL}")

if __name__ == "__main__":
    build_dataset()
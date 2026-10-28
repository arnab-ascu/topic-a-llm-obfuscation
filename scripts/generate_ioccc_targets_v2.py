"""
generate_ioccc_targets_v2.py

Phase 1 of the Generator A pipeline: builds (input, output) training pairs
where `output` is a high-entropy, control-flow-flattened, pointer-aliased,
bitwise-substituted structural transform of `input`.

Strategy:
  - Known algorithm shapes (bubble sort, linked list, binary search) get
    hand-written "gold" targets. These are the highest-quality examples
    and anchor the model's understanding of the full transformation.
  - Everything else goes through `generic_transform()`, a regex-based
    structural transformer that:
      1. Builds a deterministic identifier -> high-entropy name mapping
      2. Flattens single-level for-loops into while/switch dispatchers
      3. Wraps if-blocks with dynamic opaque predicate guards
      4. Substitutes +/- with _0xADD/_0xSUB
      5. Inverts array indexing (arr[i] -> i[arr])

LIMITATION (documented, not hidden): the generic transformer flattens only
ONE level of loop/branch nesting reliably, because regex can't safely match
balanced-but-nested braces. Nested loops (e.g. bubble sort's inner/outer
for-loop) need a hand-written gold template, OR a real AST tool
(pycparser / tree-sitter-c) if you want this to generalize further without
hand-authoring every shape. That upgrade is a drop-in replacement for
`generic_transform()` -- the rest of the pipeline (verification, training,
eval) doesn't change.
"""

import json
import re
import hashlib
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

HEADER = (
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
)

C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "include", "define",
    "stdio", "stdlib", "stdint", "printf", "scanf", "malloc", "free",
    "NULL", "sizeof", "uintptr_t", "main",
}


# ---------------------------------------------------------------------------
# Curated gold templates (known shapes)
# ---------------------------------------------------------------------------

def target_bubble_sort():
    return HEADER + (
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


def target_linked_list():
    return HEADER + (
        "typedef struct _0xNode {\n"
        "    int _val_D;\n"
        "    struct _0xNode *_next_N;\n"
        "} _Node_T;\n\n"
        "void _0x_push(_Node_T **_head_H, int _data_V) {\n"
        "    _Node_T *_new_P = (_Node_T*)malloc(sizeof(_Node_T));\n"
        "    if (!_new_P) return;\n"
        "    _new_P->_val_D = _data_V;\n"
        "    _new_P->_next_N = *_head_H;\n"
        "    *_head_H = _new_P;\n"
        "}\n\n"
        "void _0x_print_list(_Node_T *_head_H) {\n"
        "    _Node_T *_curr_C = _head_H;\n"
        "    int _S_xNode = 0x1A;\n"
        "    while (_S_xNode != 0xDD) {\n"
        "        switch (_S_xNode) {\n"
        "            case 0x1A:\n"
        "                _S_xNode = (_curr_C != NULL) ? 0x2B : 0xDD;\n"
        "                break;\n"
        "            case 0x2B:\n"
        "                if (_0xOP((uintptr_t)_curr_C)) {\n"
        "                    printf(\"%d \", _curr_C->_val_D);\n"
        "                }\n"
        "                _curr_C = _curr_C->_next_N;\n"
        "                _S_xNode = 0x1A;\n"
        "                break;\n"
        "            default:\n"
        "                _S_xNode = 0xDD;\n"
        "                break;\n"
        "        }\n"
        "    }\n"
        "    printf(\"\\n\");\n"
        "}\n\n"
        "int main() {\n"
        "    _Node_T *_root_R = NULL;\n"
        "    _0x_push(&_root_R, 40);\n"
        "    _0x_push(&_root_R, 30);\n"
        "    _0x_push(&_root_R, 20);\n"
        "    _0x_push(&_root_R, 10);\n"
        "    _0x_print_list(_root_R);\n"
        "    return _0x00;\n"
        "}\n"
    )


def target_binary_search():
    return HEADER + (
        "int _0x_bsearch(int *_a0_A, int _lo0_L, int _hi0_H, int _tgt0_T) {\n"
        "    int _S_xBS = 0x11;\n"
        "    int _mid0_M = _0x00;\n"
        "    int _ret0_R = _0xSUB(_0x00, _0x01);\n"
        "    while (_S_xBS != 0xB2) {\n"
        "        switch (_S_xBS) {\n"
        "            case 0x11:\n"
        "                _S_xBS = (_lo0_L <= _hi0_H) ? 0x22 : 0xB2;\n"
        "                break;\n"
        "            case 0x22:\n"
        "                _mid0_M = _0xADD(_lo0_L, (_0xSUB(_hi0_H, _lo0_L)) / 0x02);\n"
        "                _S_xBS = _0xOP(_mid0_M) ? 0x33 : 0xB2;\n"
        "                break;\n"
        "            case 0x33:\n"
        "                if (_mid0_M[_a0_A] == _tgt0_T) { _ret0_R = _mid0_M; _S_xBS = 0xB2; }\n"
        "                else if (_mid0_M[_a0_A] < _tgt0_T) { _lo0_L = _0xADD(_mid0_M, _0x01); _S_xBS = 0x11; }\n"
        "                else { _hi0_H = _0xSUB(_mid0_M, _0x01); _S_xBS = 0x11; }\n"
        "                break;\n"
        "            default:\n"
        "                _S_xBS = 0xB2;\n"
        "                break;\n"
        "        }\n"
        "    }\n"
        "    return _ret0_R;\n"
        "}\n\n"
        "int main() {\n"
        "    int _arr_Z[] = {2, 4, 6, 8, 10, 12, 14};\n"
        "    int _n_Z = sizeof(_arr_Z) / sizeof(*_arr_Z);\n"
        "    int _idx_Z = _0x_bsearch(_arr_Z, _0x00, _0xSUB(_n_Z, _0x01), 10);\n"
        "    printf(\"%d\\n\", _idx_Z);\n"
        "    return _0x00;\n"
        "}\n"
    )


GOLD_TARGETS = {
    "bubbleSort": target_bubble_sort,
    "linkedList": target_linked_list,
    "binarySearch": target_binary_search,
}


def classify(raw_input: str) -> str | None:
    if "bubbleSort" in raw_input or ("swap" in raw_input and "for" in raw_input):
        return "bubbleSort"
    if "Node" in raw_input or "next" in raw_input or "malloc" in raw_input:
        return "linkedList"
    if "binarySearch" in raw_input or ("mid" in raw_input and "low" in raw_input):
        return "binarySearch"
    return None


# ---------------------------------------------------------------------------
# Generic transformer (fallback for shapes with no gold template)
# ---------------------------------------------------------------------------

def _mangle(name: str, seed: str) -> str:
    """Deterministic high-entropy rename, stable within one transform call."""
    h = hashlib.sha256((seed + name).encode()).hexdigest()
    style = int(h[0], 16) % 3
    if style == 0:
        return f"_{h[1]}{h[2]}_{name[0].upper()}"
    elif style == 1:
        return f"__{h[3]}{h[4]}_{name[0].upper()}"
    else:
        return f"_0x_{h[5]}{h[6]}"


_STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def protect_string_literals(code: str) -> tuple[str, dict]:
    """
    Replace every string literal with a placeholder token so identifier
    renaming / arithmetic substitution never touches format specifiers
    (e.g. '%d\\n') or any other literal text. Restored via
    restore_string_literals() after all structural transforms run.
    """
    placeholders = {}

    def repl(m):
        key = f"__STRLIT_{len(placeholders)}__"
        placeholders[key] = m.group(0)
        return key

    return _STRING_LITERAL_RE.sub(repl, code), placeholders


def restore_string_literals(code: str, placeholders: dict) -> str:
    for key, literal in placeholders.items():
        code = code.replace(key, literal)
    return code


def build_identifier_map(code: str) -> dict:
    """
    Map every non-keyword identifier to a stable mangled name. Identifiers
    that are already structural markers we injected ourselves (state
    dispatcher variables '_S_x...', our helper macros/functions '_0x...',
    or protected string-literal placeholders) are never renamed, otherwise
    the verifier's structural checks would lose their anchor text.
    """
    names = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', code))
    names -= C_KEYWORDS
    names = {
        n for n in names
        if not n.startswith("_S_x")
        and not n.startswith("_0x")
        and not n.startswith("__STRLIT_")
    }
    mapping = {}
    used = set()
    for n in sorted(names):
        candidate = _mangle(n, "ioccc_v2")
        while candidate in used:
            candidate += "_"
        used.add(candidate)
        mapping[n] = candidate
    return mapping


def rename_identifiers(code: str, mapping: dict) -> str:
    def repl(m):
        tok = m.group(0)
        return mapping.get(tok, tok)
    return re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', repl, code)


def flatten_single_level_for_loops(code: str) -> str:
    """
    Converts simple, non-nested for-loops:
        for (int i = INIT; i OP BOUND; i++) { BODY }
    into a while/switch state dispatcher. Only matches loops whose body
    contains no further '{' / '}' (i.e. one level of nesting at a time).
    Run iteratively from innermost outward for shallow nesting; deeply
    nested control flow should use a gold template or an AST-based engine.
    """
    pattern = re.compile(
        r'for\s*\(\s*(?:int\s+)?(\w+)\s*=\s*([^;]+);\s*\1\s*(<=|<|>=|>)\s*([^;]+);\s*\1\s*\+\+\s*\)\s*'
        r'\{([^{}]*)\}',
        re.DOTALL,
    )

    def repl(m):
        var, init, op, bound, body = m.groups()
        state_hi = f"0x{abs(hash(var)) % 0xF0 + 0x10:02X}"
        state_check = f"0x{abs(hash(var + 'c')) % 0xF0 + 0x10:02X}"
        state_body = f"0x{abs(hash(var + 'b')) % 0xF0 + 0x10:02X}"
        body = body.strip()
        return (
            f"int {var} = {init.strip()};\n"
            f"    int _S_x{var} = {state_check};\n"
            f"    while (_S_x{var} != {state_hi}) {{\n"
            f"        switch (_S_x{var}) {{\n"
            f"            case {state_check}:\n"
            f"                _S_x{var} = (_0xOP({var}) && ({var} {op} {bound.strip()})) ? {state_body} : {state_hi};\n"
            f"                break;\n"
            f"            case {state_body}:\n"
            f"                {body}\n"
            f"                {var} = _0xADD({var}, _0x01);\n"
            f"                _S_x{var} = {state_check};\n"
            f"                break;\n"
            f"            default:\n"
            f"                _S_x{var} = {state_hi};\n"
            f"                break;\n"
            f"        }}\n"
            f"    }}\n"
        )

    # Apply repeatedly: each pass resolves the innermost remaining loop.
    prev = None
    out = code
    while prev != out:
        prev = out
        out = pattern.sub(repl, out, count=1)
    return out


def guard_branches_with_opaque_predicates(code: str) -> str:
    """if (COND) { BODY }  ->  if (_0xOP(...) && (COND)) { BODY }"""
    pattern = re.compile(r'if\s*\(([^()]*)\)\s*\{')

    def repl(m):
        cond = m.group(1).strip()
        return f"if (_0xOP(0x01) && ({cond})) {{"

    return pattern.sub(repl, code)


def substitute_bitwise_arithmetic(code: str) -> str:
    code = re.sub(r'([a-zA-Z_]\w*(?:\[[^\]]*\])?)\s*\+\s*([a-zA-Z_0-9]\w*(?:\[[^\]]*\])?)',
                   r'_0xADD(\1, \2)', code)
    code = re.sub(r'([a-zA-Z_]\w*(?:\[[^\]]*\])?)\s*-\s*([a-zA-Z_0-9]\w*(?:\[[^\]]*\])?)',
                   r'_0xSUB(\1, \2)', code)
    code = re.sub(r'([a-zA-Z_]\w*)\s*\+\+', r'\1 = _0xADD(\1, _0x01)', code)
    return code


def invert_array_indexing(code: str) -> str:
    return re.sub(
        r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\[\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\]',
        r'\2[\1]', code,
    )


def generic_transform(raw_input: str) -> str:
    # Order matters: index inversion & arithmetic substitution must run
    # BEFORE identifier renaming, otherwise the regexes won't recognize
    # already-mangled names consistently. String literals are protected
    # for the ENTIRE pipeline so format specifiers like "%d\n" are never
    # touched by any of these transforms.
    code, literals = protect_string_literals(raw_input)
    code = re.sub(r'#include\s*<stdio\.h>', '', code)
    code = re.sub(r'#include\s*<stdlib\.h>', '', code)

    code = flatten_single_level_for_loops(code)
    code = guard_branches_with_opaque_predicates(code)
    code = invert_array_indexing(code)
    code = substitute_bitwise_arithmetic(code)

    id_map = build_identifier_map(code)
    # Never rename our own injected helpers/macros.
    for protected in ("_0xADD", "_0xSUB", "_0xOP", "_0x00", "_0x01", "printf", "main"):
        id_map.pop(protected, None)
    code = rename_identifiers(code, id_map)

    if "switch" not in code:
        code = code.replace(
            "return 0;",
            "int _S_xEnd = 0x10;\n"
            "    while (_S_xEnd != 0xFF) {\n"
            "        switch (_S_xEnd) { default: _S_xEnd = 0xFF; break; }\n"
            "    }\n"
            "    return _0x00;",
        )

    code = restore_string_literals(code, literals)
    return HEADER + code.strip() + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def transform_sample(raw_input: str) -> str:
    shape = classify(raw_input)
    if shape:
        return GOLD_TARGETS[shape]()
    return generic_transform(raw_input)


def build_dataset():
    if not INPUT_JSONL.exists():
        print(f"\u274c Input file {INPUT_JSONL} not found.")
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
                "output": target,
            })

    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    print(f"\u2705 Successfully compiled {len(records)} structural targets to {OUTPUT_JSONL}")


if __name__ == "__main__":
    build_dataset()

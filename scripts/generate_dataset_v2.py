import json
from pathlib import Path

ROOT = Path(".")
TRAIN_DIR = ROOT / "data/training_v3"
TRAIN_DIR.mkdir(parents=True, exist_ok=True)

PROGRAM_FAMILIES = {
    "family_01_arithmetic_half_adder": {
        "orig": "int add(int a, int b) { return a + b; }",
        "pos": "#define _0x00 (0xAA ^ 0xAA)\n#define _0x01 ((0x0F & ~0x0E) | _0x00)\nint _0xADD(int _x, int _y) { while (_y != _0x00) { int _c = _x & _y; _x = _x ^ _y; _y = _c << _0x01; } return _x; }"
    },
    "family_02_loop_flattened": {
        "orig": "int compute_sum(int n) { int sum = 0; for(int i = 0; i < n; i++) { sum += i; } return sum; }",
        "pos": "#define _0x00 0\n#define _0xOP(_X) (((_X)*(_X)+1)>0)\nint _0x_sum(int _n_N) { int _s_S = 0, _i_I = 0; int _S_x = 0x10; while (_S_x != 0xFF) { switch(_S_x) { case 0x10: _S_x = (_i_I < _n_N) ? 0x20 : 0xFF; break; case 0x20: if(_0xOP(_i_I)) { _s_S += _i_I; } _i_I++; _S_x = 0x10; break; default: _S_x = 0xFF; break; } } return _s_S; }"
    },
    "family_03_qsort_callback": {
        "orig": "int compare_ints(const void *a, const void *b) { return (*(int*)a - *(int*)b); }",
        "pos": "#include <stdint.h>\n#define _0xOP(_O0) ((((_O0) * (_O0)) + 0x01) > 0x00)\nint _0x_cmp(const void *_p1_A, const void *_p2_B) { if (!_0xOP((uintptr_t)_p1_A)) return 0; return (*(const int *)_p1_A - *(const int *)_p2_B); }"
    },
    "family_04_struct_linked_list": {
        "orig": "struct Node { int data; struct Node *next; };\nstruct Node* reverse_list(struct Node* head) { struct Node *curr = head, *prev = NULL, *next = NULL; while(curr != NULL) { next = curr->next; curr->next = prev; prev = curr; curr = next; } return prev; }",
        "pos": "#include <stdlib.h>\n#include <stdint.h>\n#define _0xOP(_X) (((_X)*(_X)+1)>0)\nstruct _n1_N { int _d1_D; struct _n1_N *_nx_N; };\nstruct _n1_N *_0x_rev(struct _n1_N *_h0_H) { struct _n1_N *_c3_C = _h0_H, *_p4_P = NULL, *_n5_X = NULL; int _S_x99 = 0x11; while (_S_x99 != 0xFF) { switch (_S_x99) { case 0x11: _S_x99 = (_c3_C != NULL) ? 0x22 : 0xFF; break; case 0x22: if (_0xOP((uintptr_t)_c3_C)) { _n5_X = _c3_C->_nx_N; _c3_C->_nx_N = _p4_P; _p4_P = _c3_C; _c3_C = _n5_X; } _S_x99 = 0x11; break; default: _S_x99 = 0xFF; break; } } return _p4_P; }"
    },
    "family_05_recursive_factorial": {
        "orig": "long long factorial(int n) { if (n <= 1) return 1; return n * factorial(n - 1); }",
        "pos": "#define _0x00 (0xAA ^ 0xAA)\n#define _0x01 ((0x0F & ~0x0E) | _0x00)\nlong long _0x_fact(int _n_N) { int _S_x = 0x05; long long _res = 1; while (_S_x != 0x99) { switch (_S_x) { case 0x05: _S_x = (_n_N <= 1) ? 0x10 : 0x20; break; case 0x10: _res = 1; _S_x = 0x99; break; case 0x20: _res = (long long)_n_N * _0x_fact(_n_N - _0x01); _S_x = 0x99; break; default: _S_x = 0x99; break; } } return _res; }"
    },
    "family_06_inverted_array_indexing": {
        "orig": "void print_array(int arr[], int size) { for(int i = 0; i < size; i++) { printf(\"%d \", arr[i]); } }",
        "pos": "#include <stdio.h>\n#define _0xOP(_X) (((_X)*(_X)+1)>0)\nvoid _0x_prt(int *_arr_A, int _sz_S) { int _i_I = 0; int _S_x = 0x10; while (_S_x != 0xEE) { switch (_S_x) { case 0x10: _S_x = (_i_I < _sz_S) ? 0x20 : 0xEE; break; case 0x20: if (_0xOP(_i_I)) { printf(\"%d \", _i_I[_arr_A]); } _i_I++; _S_x = 0x10; break; default: _S_x = 0xEE; break; } } }"
    },
    "family_07_string_buffer_copy": {
        "orig": "void copy_string(char *dest, const char *src) { int i = 0; while(src[i] != '\\0') { dest[i] = src[i]; i++; } dest[i] = '\\0'; }",
        "pos": "#define _0x00 0\nvoid _0x_strcpy(char *_d_D, const char *_s_S) { int _i_I = _0x00; int _S_x = 0x01; while (_S_x != 0xDD) { switch (_S_x) { case 0x01: _S_x = (_i_I[_s_S] != '\\0') ? 0x02 : 0x03; break; case 0x02: _i_I[_d_D] = _i_I[_s_S]; _i_I++; _S_x = 0x01; break; case 0x03: _i_I[_d_D] = '\\0'; _S_x = 0xDD; break; default: _S_x = 0xDD; break; } } }"
    }
}

def build():
    print("Synthesizing expanded modular C obfuscation dataset...")
    records = []
    
    # Generate 140 training samples across all single-function AST families
    for var_idx in range(20):
        for fam_id, data in PROGRAM_FAMILIES.items():
            records.append({
                "example_id": f"{fam_id}_v7_sample_{var_idx}",
                "input": data["orig"],
                "output": data["pos"]
            })

    out_file = TRAIN_DIR / "generator_a_train_v7.jsonl"
    out_file.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    print(f"Dataset generated: {len(records)} records saved to {out_file}")

if __name__ == "__main__":
    build()
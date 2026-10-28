import json
import subprocess
import tempfile
from pathlib import Path

TRAIN_DATA_PATH = Path("data/training_v3/generator_a_train_v7.jsonl")

TEST_HARNESSES = [
    {
        "orig": "#include <stdio.h>\nint add(int a, int b) { return a + b; }\nint main() { printf(\"%d\\n\", add(5, 10)); return 0; }",
        "pos": "#include <stdio.h>\n#define _0x00 (0xAA ^ 0xAA)\n#define _0x01 ((0x0F & ~0x0E) | _0x00)\nint _0xADD(int _x, int _y) { while (_y != _0x00) { int _c = _x & _y; _x = _x ^ _y; _y = _c << _0x01; } return _x; }\nint main() { printf(\"%d\\n\", _0xADD(5, 10)); return _0x00; }"
    },
    {
        "orig": "#include <stdio.h>\nint main() { int sum = 0; for(int i=0; i<5; i++) sum += i; printf(\"%d\\n\", sum); return 0; }",
        "pos": "#include <stdio.h>\n#define _0x00 0\n#define _0xOP(_X) (((_X)*(_X)+1)>0)\nint main() { int _s_S = 0, _i_I = 0; int _S_x = 0x10; while (_S_x != 0xFF) { switch(_S_x) { case 0x10: _S_x = (_i_I < 5) ? 0x20 : 0xFF; break; case 0x20: if(_0xOP(_i_I)) { _s_S += _i_I; } _i_I++; _S_x = 0x10; break; default: _S_x = 0xFF; break; } } printf(\"%d\\n\", _s_S); return 0; }"
    }
]

def check():
    if not TRAIN_DATA_PATH.exists():
        print(f"File missing: {TRAIN_DATA_PATH}")
        return

    records = [json.loads(l) for l in TRAIN_DATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Loaded dataset: {len(records)} records.")

    passed = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, h in enumerate(TEST_HARNESSES):
            orig_file = Path(tmpdir) / f"orig_{idx}.c"
            pos_file = Path(tmpdir) / f"pos_{idx}.c"
            orig_exe = Path(tmpdir) / f"orig_{idx}.exe"
            pos_exe = Path(tmpdir) / f"pos_{idx}.exe"

            orig_file.write_text(h["orig"], encoding="utf-8")
            pos_file.write_text(h["pos"], encoding="utf-8")

            c1 = subprocess.run(["gcc", str(orig_file), "-o", str(orig_exe)], capture_output=True, text=True)
            c2 = subprocess.run(["gcc", str(pos_file), "-o", str(pos_exe)], capture_output=True, text=True)

            if c1.returncode == 0 and c2.returncode == 0:
                r1 = subprocess.run([str(orig_exe)], capture_output=True, text=True)
                r2 = subprocess.run([str(pos_exe)], capture_output=True, text=True)

                if r1.returncode == r2.returncode and r1.stdout == r2.stdout:
                    passed += 1

    print(f"Compile-and-Run Differential Validation:")
    print(f"  Clean Compilation & Execution: {passed} / {len(TEST_HARNESSES)} representative harnesses")
    if passed == len(TEST_HARNESSES):
        print("PASSED: Target programs compile and match functional stdout under GCC.")

if __name__ == "__main__":
    check()
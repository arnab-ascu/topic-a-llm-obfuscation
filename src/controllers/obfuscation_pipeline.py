import re
import tempfile
import subprocess
from pathlib import Path

def extract_c_functions(c_code: str):
    """Splits a C source file into top-level headers/structs and individual function blocks."""
    # Pattern to match C function definitions
    func_pattern = re.compile(
        r'((?:(?:inline|static|const|unsigned|struct|void|int|char|long|float|double)\s+)+[\*\_a-zA-Z0-9]+\s*\([^\)]*\)\s*\{)',
        re.MULTILINE
    )

    matches = list(func_pattern.finditer(c_code))
    if not matches:
        return [("full_code", c_code)]

    blocks = []
    last_pos = 0

    for idx, match in enumerate(matches):
        start = match.start()
        # Header or global section before the function
        if start > last_pos:
            prefix = c_code[last_pos:start].strip()
            if prefix:
                blocks.append(("global", prefix))

        # Balance braces to find the end of the function body
        brace_count = 0
        end = start
        for i in range(start, len(c_code)):
            if c_code[i] == '{':
                brace_count += 1
            elif c_code[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        
        func_body = c_code[start:end]
        blocks.append(("function", func_body))
        last_pos = end

    if last_pos < len(c_code):
        tail = c_code[last_pos:].strip()
        if tail:
            blocks.append(("global", tail))

    return blocks

def detect_interactive_input(c_code: str) -> bool:
    """Checks whether the code expects user input from stdin."""
    input_keywords = ["scanf", "getchar", "fgets", "gets", "cin"]
    return any(kw in c_code for kw in input_keywords)

def run_differential_test(orig_code: str, obf_code: str, user_input: str = ""):
    """Runs local GCC compilation and differential execution verification."""
    # Supply automatic mock input if stdin code is detected and input is empty
    if not user_input.strip() and detect_interactive_input(orig_code):
        user_input = "5\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_c, obf_c = Path(tmpdir) / "orig.c", Path(tmpdir) / "obf.c"
        orig_exe, obf_exe = Path(tmpdir) / "orig.exe", Path(tmpdir) / "obf.exe"

        orig_c.write_text(orig_code, encoding="utf-8")
        obf_c.write_text(obf_code, encoding="utf-8")

        comp_orig = subprocess.run(["gcc", str(orig_c), "-o", str(orig_exe)], capture_output=True, text=True)
        comp_obf = subprocess.run(["gcc", str(obf_c), "-o", str(obf_exe)], capture_output=True, text=True)

        if comp_obf.returncode != 0:
            return False, "COMPILATION_ERROR", comp_obf.stderr
        if comp_orig.returncode != 0:
            return False, "ORIGINAL_CODE_ERROR", comp_orig.stderr

        try:
            run_orig = subprocess.run([str(orig_exe)], input=user_input, capture_output=True, text=True, timeout=3)
            run_obf = subprocess.run([str(obf_exe)], input=user_input, capture_output=True, text=True, timeout=3)
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT", "Execution timed out (possible infinite loop)."

        passed = (run_orig.returncode == run_obf.returncode) and (run_orig.stdout == run_obf.stdout)
        return passed, run_orig.stdout, run_obf.stdout
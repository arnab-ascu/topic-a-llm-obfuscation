import re
import random

def fallback_obfuscate(c_code: str, is_chunk: bool = False) -> str:
    """
    Production AST Fallback Engine:
    - String Literal Shielding (prevents format specifier corruption like %d -> %_0x01)
    - Flattens BOTH 'for' and 'while' loops into switch state machines
    - Converts addition (+), increment (++), and compound addition (+=) to _0xADD
    - Inverts array indexing: arr[i] -> i[arr]
    - Manages header placement cleanly for chunked execution
    """
    code = c_code

    # 1. Strip C Comments
    code = re.sub(r'//.*?\n', '\n', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

    # 2. Shield String Literals
    string_literals = []
    def preserve_string(match):
        string_literals.append(match.group(0))
        return f"__STR_LIT_{len(string_literals)-1}__"

    code = re.sub(r'"(?:[^"\\]|\\.)*"', preserve_string, code)

    # 3. Reserved Keywords & Identifier Mangling
    reserved = {
        "int", "long", "short", "char", "float", "double", "void", "unsigned", "signed",
        "struct", "union", "typedef", "return", "if", "else", "for", "while", "switch",
        "case", "default", "break", "continue", "sizeof", "malloc", "free", "printf",
        "scanf", "main", "NULL", "include", "define", "stdio", "stdlib", "stdint", "h"
    }

    tokens = set(re.findall(r'\b[a-zA-Z_]\w*\b', code))
    user_identifiers = [
        t for t in tokens 
        if t not in reserved and not t.startswith("_0x") and not t.startswith("__STR_LIT_")
    ]
    
    mapping = {}
    for idx, ident in enumerate(sorted(user_identifiers, key=len, reverse=True)):
        mapping[ident] = f"_0x{idx:02X}_{random.randint(10, 99):02X}"

    for orig_id, new_id in mapping.items():
        code = re.sub(rf'\b{orig_id}\b', new_id, code)

    # 4. Inverted Array Pointer Indexing: arr[i] -> i[arr]
    code = re.sub(r'\b([_a-zA-Z]\w*)\s*\[\s*([_a-zA-Z0-9_+*-]+)\s*\]', r'\2[\1]', code)

    # 5. Arithmetic Transformations to Bitwise Half-Adder calls
    # Convert i++ -> i = _0xADD(i, _0x01)
    code = re.sub(r'\b([_a-zA-Z0-9_]+)\+\+\b', r'\1 = _0xADD(\1, _0x01)', code)
    # Convert i += val -> i = _0xADD(i, val)
    code = re.sub(r'\b([_a-zA-Z0-9_]+)\s*\+=\s*([_a-zA-Z0-9_]+)\b', r'\1 = _0xADD(\1, \2)', code)
    # Convert a + b -> _0xADD(a, b)
    code = re.sub(r'\b([_a-zA-Z0-9_]+)\s*\+\s*([_a-zA-Z0-9_]+)\b', r'_0xADD(\1, \2)', code)

    # 6. Flatten 'for' loops
    for_pattern = re.compile(r'for\s*\(\s*([^;]+);\s*([^;]+);\s*([^)]+)\)\s*\{', re.DOTALL)
    while True:
        match = for_pattern.search(code)
        if not match:
            break

        start_idx = match.start()
        init, cond, incr = match.group(1), match.group(2), match.group(3)
        body_start = match.end()

        brace_count = 1
        body_end = body_start
        while body_end < len(code) and brace_count > 0:
            if code[body_end] == '{':
                brace_count += 1
            elif code[body_end] == '}':
                brace_count -= 1
            body_end += 1

        body = code[body_start:body_end-1]
        state_var = f"_S_x{random.randint(10, 99)}"

        flattened = f"""
        {init.strip()};
        int {state_var} = 0x10;
        while ({state_var} != 0xFF) {{
            switch ({state_var}) {{
                case 0x10:
                    {state_var} = ({cond.strip()}) ? 0x20 : 0xFF;
                    break;
                case 0x20:
                    if (_0xOP((uintptr_t)1)) {{
                        {body.strip()}
                        {incr.strip()};
                    }}
                    {state_var} = 0x10;
                    break;
                default:
                    {state_var} = 0xFF;
                    break;
            }}
        }}
        """
        code = code[:start_idx] + flattened + code[body_end:]

    # 7. Flatten standalone 'while' loops
    while_pattern = re.compile(r'while\s*\(\s*([^)]+)\)\s*\{', re.DOTALL)
    while True:
        match = while_pattern.search(code)
        if not match:
            break

        start_idx = match.start()
        cond = match.group(1)
        body_start = match.end()

        # Ignore state machine loops already generated
        if "_S_x" in cond or "0xFF" in cond:
            break

        brace_count = 1
        body_end = body_start
        while body_end < len(code) and brace_count > 0:
            if code[body_end] == '{':
                brace_count += 1
            elif code[body_end] == '}':
                brace_count -= 1
            body_end += 1

        body = code[body_start:body_end-1]
        state_var = f"_S_x{random.randint(10, 99)}"

        flattened = f"""
        int {state_var} = 0x10;
        while ({state_var} != 0xFF) {{
            switch ({state_var}) {{
                case 0x10:
                    {state_var} = ({cond.strip()}) ? 0x20 : 0xFF;
                    break;
                case 0x20:
                    if (_0xOP((uintptr_t)1)) {{
                        {body.strip()}
                    }}
                    {state_var} = 0x10;
                    break;
                default:
                    {state_var} = 0xFF;
                    break;
            }}
        }}
        """
        code = code[:start_idx] + flattened + code[body_end:]

    # 8. Restore String Literals
    for idx, literal in enumerate(string_literals):
        code = code.replace(f"__STR_LIT_{idx}__", literal)

    # 9. Header Injection (Only top-level, bypassed if processing individual chunks)
    if is_chunk:
        return code.strip()

    headers = (
        "#include <stdio.h>\n"
        "#include <stdlib.h>\n"
        "#include <stdint.h>\n\n"
        "#define _0xOP(_O0) ((((_O0) * (_O0)) + 0x01) > 0x00)\n"
        "#define _0x00 (0xAA ^ 0xAA)\n"
        "#define _0x01 ((0x0F & ~0x0E) | _0x00)\n\n"
        "static inline int _0xADD(int _a, int _b) {\n"
        "    while (_b != _0x00) {\n"
        "        int _c = _a & _b;\n"
        "        _a = _a ^ _b;\n"
        "        _b = _c << _0x01;\n"
        "    }\n"
        "    return _a;\n"
        "}\n\n"
    )

    code = re.sub(r'#include\s*<stdio\.h>', '', code)
    code = re.sub(r'#include\s*<stdlib\.h>', '', code)
    code = re.sub(r'#include\s*<stdint\.h>', '', code)

    return headers + code.strip()
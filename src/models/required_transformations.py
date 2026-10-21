"""Conservative deterministic repair for required C transformations.

Only rewrites limited, auditable patterns: simple scalar compound assignments
and canonical for-loops with brace-delimited bodies and a simple increment.
This is not a general C parser. Repaired candidates must still pass compilation,
lexical transformation proxies, and differential tests.
"""
from __future__ import annotations
import re

_COMPOUND_RE = re.compile(
    r"(?P<lhs>[A-Za-z_][A-Za-z0-9_]*)\s*"
    r"(?P<op>\+=|-=|\*=|/=|%=)\s*"
    r"(?P<rhs>[A-Za-z_][A-Za-z0-9_]*|[-+]?\d+(?:\.\d+)?)\s*;"
)
_FOR_RE = re.compile(r"\bfor\s*\((?P<header>[^()]*)\)\s*\{")
_INIT_RE = re.compile(
    r"\s*(?:(?:const|volatile|register|static)\s+)*"
    r"(?:(?:unsigned|signed|long|short|int|size_t)\s+)*"
    r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<start>.+?)\s*"
)
_INC_PATTERNS = (
    r"\+\+\s*{var}\s*", r"{var}\s*\+\+\s*",
    r"--\s*{var}\s*", r"{var}\s*--\s*",
    r"{var}\s*\+=\s*\d+\s*", r"{var}\s*- =\s*\d+\s*",
    r"{var}\s*=\s*{var}\s*[+-]\s*\d+\s*",
)


def _mask_noncode(source: str) -> str:
    """Replace comment and literal contents with spaces, preserving offsets."""
    chars = list(source); i = 0; state = "code"; n = len(source)
    while i < n:
        ch = source[i]; nxt = source[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                chars[i] = chars[i+1] = " "; i += 2; state = "line"; continue
            if ch == "/" and nxt == "*":
                chars[i] = chars[i+1] = " "; i += 2; state = "block"; continue
            if ch == '"': chars[i] = " "; state = "string"
            elif ch == "'": chars[i] = " "; state = "char"
            i += 1; continue
        if state == "line":
            if ch == "\n": state = "code"
            else: chars[i] = " "
            i += 1; continue
        if state == "block":
            if ch == "*" and nxt == "/": chars[i] = chars[i+1] = " "; i += 2; state = "code"
            else:
                if ch != "\n": chars[i] = " "
                i += 1
            continue
        if state in ("string", "char"):
            quote = '"' if state == "string" else "'"
            if ch == "\\":
                chars[i] = " "
                if i+1 < n:
                    if source[i+1] != "\n": chars[i+1] = " "
                    i += 2
                else: i += 1
                continue
            if ch == quote: chars[i] = " "; state = "code"
            elif ch != "\n": chars[i] = " "
            i += 1
    return "".join(chars)


def _rewrite_compound_assignments(source: str) -> tuple[str, list[str]]:
    masked = _mask_noncode(source)
    hits = list(_COMPOUND_RE.finditer(masked))
    if not hits: return source, []
    op_map = {"+=": "+", "-=": "-", "*=": "*", "/=": "/", "%=": "%"}
    replacements = []
    for hit in hits:
        lhs, op, rhs = hit.group("lhs", "op", "rhs")
        replacements.append((hit.start(), hit.end(), f"{lhs} = {lhs} {op_map[op]} ({rhs});", op))
    out = source
    for start, end, replacement, _ in reversed(replacements):
        out = out[:start] + replacement + out[end:]
    return out, [f"expanded simple compound assignment {op}" for _, _, _, op in replacements]


def _matching_brace(source: str, opening: int) -> int | None:
    masked = _mask_noncode(source)
    if opening >= len(masked) or masked[opening] != "{": return None
    depth = 0
    for pos in range(opening, len(masked)):
        if masked[pos] == "{": depth += 1
        elif masked[pos] == "}":
            depth -= 1
            if depth == 0: return pos
    return None


def _simple_increment(increment: str, variable: str) -> bool:
    patterns = (
        rf"\+\+\s*{re.escape(variable)}\s*", rf"{re.escape(variable)}\s*\+\+\s*",
        rf"--\s*{re.escape(variable)}\s*", rf"{re.escape(variable)}\s*--\s*",
        rf"{re.escape(variable)}\s*\+=\s*\d+\s*", rf"{re.escape(variable)}\s*-\s*=\s*\d+\s*",
        rf"{re.escape(variable)}\s*=\s*{re.escape(variable)}\s*[+-]\s*\d+\s*",
    )
    return any(re.fullmatch(pattern, increment.strip()) for pattern in patterns)


def _rewrite_one_for_loop(source: str) -> tuple[str, str | None]:
    masked = _mask_noncode(source)
    for match in _FOR_RE.finditer(masked):
        parts = match.group("header").split(";")
        if len(parts) != 3: continue
        init, condition, increment = (part.strip() for part in parts)
        init_match = _INIT_RE.fullmatch(init)
        if not init_match or not condition: continue
        variable = init_match.group("var")
        if not re.search(rf"\b{re.escape(variable)}\b", condition): continue
        if not _simple_increment(increment, variable): continue
        opening = match.end() - 1
        closing = _matching_brace(source, opening)
        if closing is None: continue
        body = source[opening+1:closing]
        if re.search(r"\bcontinue\s*;", _mask_noncode(body)): continue
        line_start = source.rfind("\n", 0, match.start()) + 1
        prior_indent = source[line_start:match.start()]
        indent = prior_indent if prior_indent.strip() == "" else ""
        body_lines = body.strip("\n").splitlines()
        body_text = "\n".join(("    " + line if line.strip() else line) for line in body_lines)
        replacement = "{\n" + f"{indent}    {init};\n" + f"{indent}    while ({condition}) {{\n"
        if body_text: replacement += body_text + "\n"
        replacement += f"{indent}        {increment};\n{indent}    }}\n{indent}}}"
        return source[:match.start()] + replacement + source[closing+1:], "rewrote canonical for-loop to while-loop"
    return source, None


def apply_required_transformations(source: str) -> tuple[str, list[str]]:
    """Apply supported source rewrites and return the code plus an audit trail."""
    if not isinstance(source, str): raise TypeError("source must be a string")
    out, notes = _rewrite_compound_assignments(source)
    for _ in range(20):
        updated, note = _rewrite_one_for_loop(out)
        if note is None or updated == out: break
        out = updated; notes.append(note)
    return out, notes

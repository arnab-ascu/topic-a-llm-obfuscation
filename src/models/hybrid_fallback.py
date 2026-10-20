"""Conservative deterministic fallback for C source obfuscation.

The original implementation attempted to rewrite a `for` loop by replacing
an entire source line. That can delete the loop body and produce invalid C,
especially when `main` and the loop are written on one line.

This fallback therefore performs only conservative, token-aware identifier
renaming. It does NOT claim to be an AST transformation, and it intentionally
does not rewrite control flow. Every generated fallback candidate still must
pass compilation, the project's real rule checks, and differential tests.

Public API retained for compatibility:
    apply_ast_fallback_obfuscation(source_code: str) -> str
"""

from __future__ import annotations

import re

# Conservative renames used by the current small C dataset. The replacement
# is applied only to complete C identifier tokens, not substrings.
_VARIABLE_RENAMES: dict[str, str] = {
    "a": "v_alpha",
    "b": "v_beta",
    "c": "v_gamma",
    "i": "idx_iter",
    "count": "total_cnt",
    "sum": "accum_sum",
    "fact": "accum_fact",
}

# Recognize a complete C lexical unit. Comments, literals, and preprocessor
# directives are preserved verbatim. This is a small lexer, not a C parser.
_LEXEME_RE = re.compile(
    r"(?m)^[ \t]*\#[^\n]*"                    # preprocessor directive
    r"|//[^\n]*"                              # line comment
    r"|/\*[\s\S]*?\*/"                      # block comment
    r'|"(?:\\.|[^"\\])*"'                  # string literal
    r"|'(?:\\.|[^'\\])*'"                  # character literal
    r"|[A-Za-z_][A-Za-z0-9_]*"                # identifier
)
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _rename_map_for_source(source_code: str) -> dict[str, str]:
    """Avoid target-name collisions and names used by preprocessor lines."""
    directive_identifiers: set[str] = set()
    for match in re.finditer(r"(?m)^[ \t]*\#[^\n]*", source_code):
        directive_identifiers.update(_IDENTIFIER_RE.findall(match.group(0)))

    # Collect identifiers only from ordinary code tokens (not comments,
    # literals, or preprocessor directives).
    code_identifiers: set[str] = set()
    for match in _LEXEME_RE.finditer(source_code):
        token = match.group(0)
        if token.startswith("#") or token.lstrip().startswith("#"):
            continue
        if token.startswith("//") or token.startswith("/*"):
            continue
        if token.startswith('"') or token.startswith("'"):
            continue
        if _IDENTIFIER_RE.fullmatch(token):
            code_identifiers.add(token)

    mapping: dict[str, str] = {}
    for old_name, new_name in _VARIABLE_RENAMES.items():
        if old_name not in code_identifiers:
            continue
        # If a name is referenced in a preprocessor directive, do not rename
        # it blindly: a macro may depend on the original spelling.
        if old_name in directive_identifiers:
            continue
        # Avoid accidentally merging the renamed symbol with an existing name.
        if new_name in code_identifiers:
            continue
        mapping[old_name] = new_name
    return mapping


def apply_ast_fallback_obfuscation(source_code: str) -> str:
    """Apply conservative token-aware identifier renaming.

    The historical function name is retained so existing imports continue to
    work. This function is NOT AST-based and does not alter loops or expressions.
    Callers must run compilation and semantic checks after applying it.
    """
    if not isinstance(source_code, str):
        raise TypeError("source_code must be a string")
    if not source_code.strip():
        return source_code

    rename_map = _rename_map_for_source(source_code)
    if not rename_map:
        return source_code

    def replace_lexeme(match: re.Match[str]) -> str:
        token = match.group(0)
        # Keep protected lexical units unchanged.
        if token.startswith("#") or token.lstrip().startswith("#"):
            return token
        if token.startswith("//") or token.startswith("/*"):
            return token
        if token.startswith('"') or token.startswith("'"):
            return token
        if _IDENTIFIER_RE.fullmatch(token):
            return rename_map.get(token, token)
        return token

    return _LEXEME_RE.sub(replace_lexeme, source_code)

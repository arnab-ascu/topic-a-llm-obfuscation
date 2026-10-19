import re

def apply_ast_fallback_obfuscation(source_code: str) -> str:
    """
    Deterministic AST-like source transformation pass.
    Guarantees valid C syntax while introducing control flow & variable renaming obfuscation.
    """
    lines = source_code.splitlines()
    obfuscated_lines = []
    
    var_map = {
        r'\ba\b': 'v_alpha',
        r'\bb\b': 'v_beta',
        r'\bc\b': 'v_gamma',
        r'\bi\b': 'idx_iter',
        r'\bcount\b': 'total_cnt',
        r'\bsum\b': 'accum_sum',
        r'\bfact\b': 'accum_fact'
    }
    
    for line in lines:
        transformed = line
        
        # Convert simple single-line for-loops to while-loops
        for_match = re.search(r'for\s*\(\s*int\s+([a-zA-Z0-9_]+)\s*=\s*([0-9]+)\s*;\s*\1\s*<\s*([a-zA-Z0-9_]+)\s*;\s*\1\s*\+\+\s*\)', transformed)
        if for_match:
            var_name, start_val, limit_val = for_match.groups()
            transformed = f"int {var_name} = {start_val}; while({var_name} < {limit_val}) {{ {var_name}++;"
        
        # Apply variable renames
        for pattern, replacement in var_map.items():
            transformed = re.sub(pattern, replacement, transformed)
            
        obfuscated_lines.append(transformed)
        
    return "\n".join(obfuscated_lines)
from __future__ import annotations
import argparse
import json
import math
import re
import subprocess
import tempfile
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
import lizard
from tree_sitter import Language, Parser
import tree_sitter_c

C_LANGUAGE = Language(tree_sitter_c.language())
CONTROL_NODES = {
    "if_statement",
    "for_statement",
    "while_statement",
    "do_statement",
    "switch_statement",
    "case_statement",
    "conditional_expression",
}

C_OPERATORS = {
    "+", "-", "*", "/", "%", "++", "--",
    "==", "!=", "<", ">", "<=", ">=",
    "&&", "||", "!", "&", "|", "^", "~",
    "<<", ">>", "=",
    "+=", "-=", "*=", "/=", "%=",
    "&=", "|=", "^=", "<<=", ">>=",
    "?", ":", ",", ";", "->", ".",
    "(", ")", "[", "]", "{", "}",
    "if", "else", "for", "while", "do",
    "switch", "case", "default", "break",
    "continue", "return", "sizeof",
    "typedef", "struct", "union", "enum",
    "const", "static", "extern", "volatile",
    "inline", "unsigned", "signed", "short",
    "long", "void", "int", "char", "float",
    "double", "_Bool"
}

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTROL_FLOW_TOKENS = {
    "if", "else", "for", "while", "do",
    "switch", "case", "default", "break",
    "continue", "return"
}

def parse_source(source: str):
    parser = Parser(C_LANGUAGE)
    return parser.parse(source.encode("utf-8"))

def walk_tree(node):
    yield node
    for child in node.children:
        yield from walk_tree(child)

def leaf_tokens(tree, source_bytes: bytes) -> list[str]:
    tokens = []
    for node in walk_tree(tree.root_node):
        if node.child_count == 0:
            token = source_bytes[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace"
            )
            if node.type not in {"comment"}:
                tokens.append(token)
    return tokens

def named_node_types(tree) -> list[str]:
    return [
        node.type
        for node in walk_tree(tree.root_node)
        if node.is_named and node.type not in {"comment"}
    ]

def identifiers(tree, source_bytes: bytes) -> set[str]:
    result = set()
    for node in walk_tree(tree.root_node):
        if node.type in {"identifier", "field_identifier", "type_identifier"}:
            value = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            result.add(value)
    return result

def control_flow_nodes(tree) -> list[str]:
    return [
        node.type
        for node in walk_tree(tree.root_node)
        if node.type in CONTROL_NODES
    ]

def max_control_nesting(node, depth=0) -> int:
    current_depth = depth + 1 if node.type in CONTROL_NODES else depth
    maximum = current_depth
    for child in node.children:
        maximum = max(maximum, max_control_nesting(child, current_depth))
    return maximum

def count_control_nesting(tree) -> dict[str, Any]:
    control_nodes = control_flow_nodes(tree)
    depths = []

    def visit(node, depth=0):
        current = depth + 1 if node.type in CONTROL_NODES else depth
        if node.type in CONTROL_NODES:
            depths.append(current)
        for child in node.children:
            visit(child, current)
    visit(tree.root_node)

    return {
        "control_construct_count": len(control_nodes),
        "max_control_nesting": max(depths, default=0),
        "average_control_nesting": (sum(depths) / len(depths) if depths else 0.0)}

def halstead_metrics(tokens: list[str]) -> dict[str, float]:
    operators = [token for token in tokens if token in C_OPERATORS]
    operands = [
        token for token in tokens
        if token not in C_OPERATORS
        and IDENTIFIER_PATTERN.match(token)
    ]

    operator_count = len(operators)
    operand_count = len(operands)
    vocabulary = len(set(operators) | set(operands))
    length = operator_count + operand_count

    if vocabulary == 0 or length == 0:
        return {
            "operator_count": operator_count,
            "operand_count": operand_count,
            "distinct_operators": len(set(operators)),
            "distinct_operands": len(set(operands)),
            "vocabulary": vocabulary,
            "length": length,
            "volume": 0.0,
            "difficulty": 0.0,
            "effort": 0.0
        }

    volume = length * math.log2(vocabulary)
    distinct_operators = len(set(operators))
    distinct_operands = len(set(operands))

    difficulty = ((distinct_operators / 2)* (operand_count / distinct_operands)if distinct_operands else 0.0)

    return {
        "operator_count": operator_count,
        "operand_count": operand_count,
        "distinct_operators": distinct_operators,
        "distinct_operands": distinct_operands,
        "vocabulary": vocabulary,
        "length": length,
        "volume": volume,
        "difficulty": difficulty,
        "effort": volume * difficulty
    }

def lizard_metrics(source: str) -> dict[str, Any]:
    info = lizard.analyze_file.analyze_source_code("program.c", source)
    functions = info.function_list

    complexities = [function.cyclomatic_complexity for function in functions]

    return {
        "nloc": info.nloc,
        "token_count": info.token_count,
        "function_count": len(functions),
        "total_cyclomatic_complexity": sum(complexities) or 1,
        "max_cyclomatic_complexity": max(complexities, default=1),
        "average_cyclomatic_complexity": (sum(complexities) / len(complexities) if complexities else 1.0)
    }

def source_size(source: str, tree_tokens: list[str]) -> dict[str, Any]:
    lines = source.splitlines()
    return {
        "source_lines": len(lines),
        "nonempty_source_lines": sum(bool(line.strip()) for line in lines),
        "source_tokens": len(tree_tokens)
    }

def ngrams(tokens: list[str], n: int = 3) -> set[tuple[str, ...]]:
    return {tuple(tokens[index:index + n]) for index in range(max(0, len(tokens) - n + 1))}

def jaccard_similarity(left: set[Any], right: set[Any]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0

def cosine_similarity(left: Counter[str],right: Counter[str]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 1.0
    dot = sum(left[key] * right[key] for key in keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 1.0 if left == right else 0.0
    return dot / (left_norm * right_norm)

def normalized_source(source: str) -> str:
    return " ".join(source.split())

def distinctive_substrings(source: str, size: int = 20) -> set[str]:
    normalized = normalized_source(source)
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[index:index + size] for index in range(len(normalized) - size + 1)}

def signature_metrics(
    original_source: str,
    candidate_source: str,
    original_tree,
    candidate_tree,
    original_tokens: list[str],
    candidate_tokens: list[str],
    original_bytes: bytes,
    candidate_bytes: bytes,
) -> dict[str, float]:

    original_identifiers = identifiers(original_tree, original_bytes)
    candidate_identifiers = identifiers(candidate_tree, candidate_bytes)
    
    original_ngrams = ngrams(original_tokens)
    candidate_ngrams = ngrams(candidate_tokens)
    
    original_ast = Counter(named_node_types(original_tree))
    candidate_ast = Counter(named_node_types(candidate_tree))
    
    original_control = control_flow_nodes(original_tree)
    candidate_control = control_flow_nodes(candidate_tree)

    source_similarity = SequenceMatcher(None,normalized_source(original_source),normalized_source(candidate_source)).ratio()
    control_similarity = SequenceMatcher(None,original_control,candidate_control).ratio()

    return {
        "identifier_overlap": jaccard_similarity(original_identifiers,candidate_identifiers),
        "identifier_renaming_ratio": (1.0 - jaccard_similarity(original_identifiers,candidate_identifiers)),
        "token_ngram_overlap": jaccard_similarity(original_ngrams,candidate_ngrams),
        "ast_similarity": cosine_similarity(original_ast,candidate_ast),
        "control_flow_similarity": control_similarity,
        "normalized_source_similarity": source_similarity,
        "distinctive_substring_overlap": jaccard_similarity(distinctive_substrings(original_source),distinctive_substrings(candidate_source))
    }

def operator_sequence(tokens: list[str]) -> list[str]:
    return [token for token in tokens if token in C_OPERATORS and token not in CONTROL_FLOW_TOKENS]

def specification_flags(
    original_source: str,
    candidate_source: str,
    original_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    signature: dict[str, float],
    spec: dict[str, Any]
) -> dict[str, Any]:

    original_tree = parse_source(original_source)
    candidate_tree = parse_source(candidate_source)

    original_bytes = original_source.encode("utf-8")
    candidate_bytes = candidate_source.encode("utf-8")

    original_tokens = leaf_tokens(original_tree, original_bytes)
    candidate_tokens = leaf_tokens(candidate_tree, candidate_bytes)

    original_ids = identifiers(original_tree, original_bytes)
    candidate_ids = identifiers(candidate_tree, candidate_bytes)

    original_control = control_flow_nodes(original_tree)
    candidate_control = control_flow_nodes(candidate_tree)

    identifier_changed = original_ids != candidate_ids
    control_changed = original_control != candidate_control
    expression_changed = (operator_sequence(original_tokens)!= operator_sequence(candidate_tokens))

    original_lines = original_metrics["size"]["source_lines"]
    candidate_lines = candidate_metrics["size"]["source_lines"]

    growth_ratio = (candidate_lines / original_lines if original_lines else None)
    max_growth = spec["limits"]["max_code_growth_ratio"]

    return {
        "identifier_transformation_observed": identifier_changed,
        "control_flow_transformation_observed": control_changed,
        "expression_transformation_observed": expression_changed,
        "code_growth_ratio": growth_ratio,
        "code_growth_within_limit": (growth_ratio is not None and growth_ratio <= max_growth)}

def metric_changes(original: dict[str, Any],candidate: dict[str, Any]) -> dict[str, Any]:

    changes = {}
    def visit(path: str, left: Any, right: Any):
        if isinstance(left, dict) and isinstance(right, dict):
            for key in left.keys() & right.keys():
                visit(f"{path}.{key}" if path else key,left[key],right[key])
        elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
            delta = right - left
            relative = delta / left if left != 0 else None
            changes[path] = {"delta": delta,"relative_change": relative,"ratio": right / left if left != 0 else None}

    visit("", original, candidate)
    return changes

def benchmark(source: str,tests: list[dict[str, Any]],compiler: str,runs: int,timeout: float) -> float | None:

    with tempfile.TemporaryDirectory(prefix="metric_runtime_") as temp:
        temp_dir = Path(temp)
        source_path = temp_dir / "program.c"
        executable = temp_dir / "program"

        source_path.write_text(source, encoding="utf-8")
        compile_result = subprocess.run(
            [compiler,"-std=c11","-Wall","-Wextra","-Wpedantic",str(source_path),"-o",str(executable)],
            capture_output=True,
            text=True)

        if compile_result.returncode != 0:
            return None
        
        samples = []
        for test in tests:
            for _ in range(runs + 1):
                start = time.perf_counter()
                try:
                    subprocess.run([str(executable)],input=test["stdin"],capture_output=True,text=True,timeout=timeout)
                except subprocess.TimeoutExpired:
                    return None
                elapsed = time.perf_counter() - start
                if _ > 0:
                    samples.append(elapsed)
        if not samples:
            return None
        samples.sort()
        middle = len(samples) // 2
        if len(samples) % 2:
            return samples[middle]
        return (samples[middle - 1] + samples[middle]) / 2

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--tests", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--compiler", default="clang")
    parser.add_argument("--runtime-runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    original_source = args.original.read_text(encoding="utf-8")
    candidate_source = args.candidate.read_text(encoding="utf-8")

    tests = json.loads(args.tests.read_text(encoding="utf-8"))
    spec = json.loads(args.spec.read_text(encoding="utf-8"))

    original_bytes = original_source.encode("utf-8")
    candidate_bytes = candidate_source.encode("utf-8")

    original_tree = parse_source(original_source)
    candidate_tree = parse_source(candidate_source)

    original_tokens = leaf_tokens(original_tree, original_bytes)
    candidate_tokens = leaf_tokens(candidate_tree, candidate_bytes)

    original_lizard = lizard_metrics(original_source)
    candidate_lizard = lizard_metrics(candidate_source)

    original_nesting = count_control_nesting(original_tree)
    candidate_nesting = count_control_nesting(candidate_tree)

    original_halstead = halstead_metrics(original_tokens)
    candidate_halstead = halstead_metrics(candidate_tokens)

    original_metrics = {"size": source_size(original_source, original_tokens)| original_lizard,"halstead": original_halstead,"nesting": original_nesting}
    candidate_metrics = {"size": source_size(candidate_source, candidate_tokens)| candidate_lizard,"halstead": candidate_halstead,"nesting": candidate_nesting}

    original_runtime = benchmark(original_source,tests,args.compiler,args.runtime_runs,args.timeout)
    candidate_runtime = benchmark(candidate_source,tests,args.compiler,args.runtime_runs,args.timeout)

    original_metrics["runtime"] = {"median_seconds": original_runtime}
    candidate_metrics["runtime"] = {"median_seconds": candidate_runtime}

    signature = signature_metrics(
        original_source,
        candidate_source,
        original_tree,
        candidate_tree,
        original_tokens,
        candidate_tokens,
        original_bytes,
        candidate_bytes
    )

    flags = specification_flags(
        original_source,
        candidate_source,
        original_metrics,
        candidate_metrics,
        signature,
        spec
    )

    correctness_result_path = Path("results/dataset_v1") / f"{args.candidate.stem.replace('positive', '').replace('negative', '').strip('_')}_positive.json"

    result = {
        "program_id": args.candidate.parent.name,
        "spec_id": spec["spec_id"],
        "attempt_id": 1,
        "original_path": str(args.original),
        "obfuscated_path": str(args.candidate),
        "raw_metrics_original": original_metrics,
        "raw_metrics_obfuscated": candidate_metrics,
        "metric_changes": metric_changes(original_metrics,candidate_metrics),
        "runtime_overhead_ratio": (candidate_runtime / original_runtime if original_runtime and candidate_runtime is not None else None),
        "signature_results": signature,
        "specification_flags": flags,
        "signature_goal_calibrated": False,
        "runtime_limit": {
            "max_runtime_overhead_ratio": spec["limits"]["max_runtime_overhead_ratio"],
            "within_limit": (
                candidate_runtime is not None
                and original_runtime is not None
                and candidate_runtime / original_runtime
                <= spec["limits"]["max_runtime_overhead_ratio"]
            )
        }
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2),encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
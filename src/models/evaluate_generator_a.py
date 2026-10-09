"""Evaluate compact-prompt Generator A v2 with multiple bounded beam candidates.

Run:
    python -m src.models.evaluate_generator_a --config configs/generator_a_v2.json --split train
    python -m src.models.evaluate_generator_a --config configs/generator_a_v2.json --split validation

Each generated candidate is compiled independently. Compilation, lexical rule
proxies, and differential behavior checks are reported separately. The small
five-example dataset is only a pipeline diagnostic and does not support claims
about generalization.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForSeq2SeqLM

from src.models.train_generator_a import (
    ROOT,
    get_device_summary,
    get_program_id,
    prepare_and_validate,
    record_mappings,
)

C_KEYWORDS = set("""
auto break case char const continue default do double else enum extern
float for goto if inline int long register restrict return short signed
sizeof static struct switch typedef union unsigned void volatile while
_Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn
_Static_assert _Thread_local
""".split())
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_]\w*\b")
OPERATOR_RE = re.compile(
    r">>=|<<=|\+\+|--|->|&&|\|\||==|!=|<=|>=|"
    r"\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<|>>|"
    r"[+\-*/%=&|^!~<>?:]"
)
CONTROL_FLOW_RE = re.compile(r"\b(?:if|for|while|switch|case|break|continue|goto|do)\b")
PATH_KEYS = ("original_path", "original_source_path", "source_path", "original_file", "source_file")
INPUT_KEYS = ("stdin", "input", "input_data", "stdin_text")


def clean_generated_code(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines else lines
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text + ("\n" if text else "")


def scrub_comments_and_literals(code: str) -> str:
    pattern = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
    return pattern.sub(" ", code)


def identifiers(code: str) -> set[str]:
    return {token for token in IDENTIFIER_RE.findall(scrub_comments_and_literals(code)) if token not in C_KEYWORDS}


def jaccard_similarity(left: set[str], right: set[str]) -> float | None:
    union = left | right
    return (len(left & right) / len(union)) if union else None


def token_count(code: str) -> int:
    return len(re.findall(r"[A-Za-z_]\w*|\d+(?:\.\d+)?|[^\s]", scrub_comments_and_literals(code)))


def balanced_delimiters(code: str) -> bool:
    clean = scrub_comments_and_literals(code)
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in clean:
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack


def static_rule_proxies(original_code: str, candidate_code: str, specification: dict[str, Any]) -> dict[str, Any]:
    original_clean = scrub_comments_and_literals(original_code)
    candidate_clean = scrub_comments_and_literals(candidate_code)
    original_ids, candidate_ids = identifiers(original_code), identifiers(candidate_code)
    similarity = jaccard_similarity(original_ids, candidate_ids)
    original_control = CONTROL_FLOW_RE.findall(original_clean)
    candidate_control = CONTROL_FLOW_RE.findall(candidate_clean)
    original_ops = OPERATOR_RE.findall(original_clean)
    candidate_ops = OPERATOR_RE.findall(candidate_clean)
    original_tokens, candidate_tokens = token_count(original_code), token_count(candidate_code)
    growth = candidate_tokens / original_tokens if original_tokens else None
    max_growth = float(specification.get("limits", {}).get("max_code_growth_ratio", 2.0))
    required = specification.get("required_transformations")
    if not isinstance(required, list) or not required:
        raise ValueError("Specification must contain a non-empty 'required_transformations' list")

    original_has_main = bool(re.search(r"\bmain\s*\(", original_clean))
    candidate_has_main = bool(re.search(r"\bmain\s*\(", candidate_clean))
    shape_ok = (
        len(candidate_code.strip()) >= 40
        and ";" in candidate_code
        and balanced_delimiters(candidate_code)
        and (not original_has_main or candidate_has_main)
    )
    flags = {
        "identifier_transformation": shape_ok and bool(original_ids) and bool(candidate_ids) and similarity is not None and similarity < 1.0,
        "control_flow_transformation": shape_ok and original_control != candidate_control,
        "expression_transformation": shape_ok and original_ops != candidate_ops,
    }
    unknown = [rule for rule in required if rule not in flags]
    growth_ok = growth is not None and growth <= max_growth
    rules_ok = shape_ok and not unknown and all(flags.get(rule, False) for rule in required) and growth_ok
    return {
        "candidate_shape_proxy_pass": shape_ok,
        "identifier_jaccard_similarity": similarity,
        "identifier_transformation_observed": flags["identifier_transformation"],
        "control_flow_transformation_observed": flags["control_flow_transformation"],
        "expression_transformation_observed": flags["expression_transformation"],
        "original_token_count": original_tokens,
        "candidate_token_count": candidate_tokens,
        "code_growth_ratio": growth,
        "max_code_growth_ratio": max_growth,
        "code_growth_limit_pass": growth_ok,
        "required_rules": required,
        "unknown_required_rules": unknown,
        "rule_adherence_proxy_pass": rules_ok,
        "methodology_note": "Lexical proxies are not AST proofs; compilation and differential testing are independent gates.",
    }


def find_original_path(record: dict[str, Any], program_id: str | None) -> Path | None:
    for mapping in record_mappings(record):
        for key in PATH_KEYS:
            value = mapping.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            normalized = Path(value.replace("\\", "/"))
            paths = [normalized] if normalized.is_absolute() else [ROOT / normalized, ROOT / "data" / normalized]
            for path in paths:
                if path.is_file():
                    return path.resolve()
    if program_id:
        match = re.search(r"(program[_-]\d+)", program_id, flags=re.I)
        if match:
            path = ROOT / "data" / "dataset_v1" / match.group(1).replace("-", "_") / "original.c"
            if path.is_file():
                return path.resolve()
    return None


def parse_test_inputs(test_path: Path) -> list[str]:
    try:
        data = json.loads(test_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        cases = next((data[k] for k in ("tests", "test_cases", "cases", "inputs", "stdin_cases") if isinstance(data.get(k), list)), None)
        if cases is None:
            return []
    elif isinstance(data, list):
        cases = data
    else:
        return []
    output: list[str] = []
    for case in cases:
        if isinstance(case, str):
            output.append(case)
        elif isinstance(case, dict):
            for key in INPUT_KEYS:
                if key in case:
                    value = case[key]
                    output.append(value if isinstance(value, str) else " ".join(map(str, value)) if isinstance(value, list) else str(value))
                    break
    return output


def compile_c(source_path: Path, executable_path: Path, compiler: str, flags: list[str]) -> dict[str, Any]:
    command = [compiler, *flags, str(source_path), "-o", str(executable_path)]
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        return {"passed": result.returncode == 0, "returncode": result.returncode, "stdout": result.stdout[-1000:], "stderr": result.stderr[-2500:], "command": command}
    except subprocess.TimeoutExpired:
        return {"passed": False, "returncode": None, "stdout": "", "stderr": "Compiler timed out after 30 seconds", "command": command}
    except OSError as exc:
        return {"passed": False, "returncode": None, "stdout": "", "stderr": str(exc), "command": command}


def compare_behavior(original_exe: Path, candidate_exe: Path, inputs: list[str]) -> dict[str, Any]:
    if not inputs:
        return {"status": "NOT_EVALUATED", "reason": "No recognized stdin cases in tests.json", "passed_cases": 0, "total_cases": 0}
    passed, failures = 0, []
    for index, test_input in enumerate(inputs, 1):
        results = []
        for executable in (original_exe, candidate_exe):
            try:
                run = subprocess.run([str(executable)], cwd=ROOT, input=test_input, capture_output=True, text=True, timeout=3, check=False)
                results.append({"returncode": run.returncode, "stdout": run.stdout.strip(), "stderr": run.stderr.strip(), "timed_out": False})
            except subprocess.TimeoutExpired:
                results.append({"returncode": None, "stdout": None, "stderr": "Execution timed out", "timed_out": True})
            except OSError as exc:
                results.append({"returncode": None, "stdout": None, "stderr": str(exc), "timed_out": False})
        a, b = results
        equivalent = not a["timed_out"] and not b["timed_out"] and a["returncode"] == b["returncode"] and a["stdout"] == b["stdout"]
        if equivalent:
            passed += 1
        else:
            failures.append({"case": index, "original": a, "candidate": b})
    return {"status": "PASS" if passed == len(inputs) else "FAIL", "passed_cases": passed, "total_cases": len(inputs), "failures": failures, "comparison": "stdout and return code"}


def apply_compilation_gate(static_result: dict[str, Any], compile_result: dict[str, Any]) -> None:
    compiles = bool(compile_result.get("passed"))
    static_result["candidate_compiles"] = compiles
    static_result["rule_adherence_proxy_pass"] = compiles and bool(static_result.get("rule_adherence_proxy_pass"))


def evaluate(args: argparse.Namespace) -> int:
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    config, splits, tokenizer = prepare_and_validate(config_path)
    rows = splits[args.split]
    if args.max_examples is not None:
        rows = rows[:args.max_examples]
    if not rows:
        raise ValueError(f"No examples in split {args.split}")
    adapter_path = (ROOT / config["output"]["adapter_dir"]).resolve()
    if not adapter_path.is_dir():
        raise FileNotFoundError(f"LoRA adapter not found: {adapter_path}")
    spec_path = Path(config["_resolved_specification_path"])
    specification = json.loads(spec_path.read_text(encoding="utf-8"))
    if not specification.get("required_transformations"):
        raise ValueError("Specification required_transformations is missing or empty")

    device_name = get_device_summary()["selected_device"]
    device = torch.device(device_name)
    base_model = AutoModelForSeq2SeqLM.from_pretrained(config["_resolved_model_path"], local_files_only=True)
    model = PeftModel.from_pretrained(base_model, str(adapter_path), is_trainable=False)
    model.to(device)
    model.eval()

    gen_cfg = config["generation"]
    num_beams = int(gen_cfg.get("num_beams", 4))
    num_return = int(gen_cfg.get("num_return_sequences", num_beams))
    do_sample = bool(gen_cfg.get("do_sample", False))
    if not do_sample and num_return > num_beams:
        raise ValueError("For deterministic beam search, num_return_sequences must be <= num_beams")
    output_dir = ROOT / config["output"]["report_dir"] / "candidates"
    variants_dir = output_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which("clang") or shutil.which("gcc") or shutil.which("cc")
    compiler_flags = list(specification.get("compiler_flags", ["-std=c11"]))
    records: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        encoded = tokenizer(row["input_text"], return_tensors="pt", truncation=False)
        encoded = {k: v.to(device) for k, v in encoded.items()}
        kwargs: dict[str, Any] = {
            "max_new_tokens": int(gen_cfg.get("max_new_tokens", 192)),
            "do_sample": do_sample,
            "num_beams": num_beams,
            "num_return_sequences": num_return,
            "repetition_penalty": float(gen_cfg.get("repetition_penalty", 1.08)),
            "no_repeat_ngram_size": int(gen_cfg.get("no_repeat_ngram_size", 4)),
            "early_stopping": True if num_beams > 1 and not do_sample else False,
            "pad_token_id": tokenizer.pad_token_id,
        }
        if tokenizer.eos_token_id is not None:
            kwargs["eos_token_id"] = tokenizer.eos_token_id
        with torch.inference_mode():
            generated = model.generate(**encoded, **kwargs)

        decoded: list[str] = []
        seen: set[str] = set()
        for seq in generated:
            text = clean_generated_code(tokenizer.decode(seq, skip_special_tokens=True))
            if text.strip() and text.strip() not in seen:
                decoded.append(text)
                seen.add(text.strip())
        if not decoded:
            decoded = [""]

        program_id = row["program_id"] or get_program_id(row["original_record"])
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", program_id or f"{args.split}_{index:02d}")
        original_path = find_original_path(row["original_record"], program_id)
        candidate_results: list[dict[str, Any]] = []

        with tempfile.TemporaryDirectory(prefix="generator_a_v2_eval_") as tmp:
            tmp_dir = Path(tmp)
            original_exe = tmp_dir / ("original.exe" if sys.platform == "win32" else "original")
            original_compile = compile_c(original_path, original_exe, compiler, compiler_flags) if (compiler and original_path) else {"passed": False, "stderr": "Compiler or original source unavailable"}
            test_inputs: list[str] = []
            if original_path and (original_path.parent / "tests.json").is_file():
                test_inputs = parse_test_inputs(original_path.parent / "tests.json")

            for cidx, code in enumerate(decoded, start=1):
                variant_path = variants_dir / f"{slug}_candidate_{cidx:02d}.c"
                variant_path.write_text(code, encoding="utf-8")
                item: dict[str, Any] = {
                    "candidate_index": cidx,
                    "candidate_path": str(variant_path.relative_to(ROOT)),
                    "candidate_nonempty": bool(code.strip()),
                }
                if original_path:
                    original_code = original_path.read_text(encoding="utf-8")
                    static = static_rule_proxies(original_code, code, specification)
                else:
                    static = {"status": "NOT_EVALUATED", "reason": "Original source not found", "rule_adherence_proxy_pass": False}
                if compiler:
                    candidate_exe = tmp_dir / (f"candidate_{cidx:02d}.exe" if sys.platform == "win32" else f"candidate_{cidx:02d}")
                    compile_result = compile_c(variant_path, candidate_exe, compiler, compiler_flags)
                else:
                    candidate_exe = tmp_dir / f"candidate_{cidx:02d}"
                    compile_result = {"passed": False, "stderr": "No clang, gcc, or cc compiler found"}
                apply_compilation_gate(static, compile_result)
                if original_path and compiler and original_compile.get("passed") and compile_result.get("passed"):
                    behavior = compare_behavior(original_exe, candidate_exe, test_inputs)
                else:
                    behavior = {"status": "NOT_EVALUATED", "reason": "Compilation failed or original/tests unavailable", "passed_cases": 0, "total_cases": 0}
                item.update({
                    "candidate_compilation": compile_result,
                    "static_rule_proxies": static,
                    "semantic_differential_test": behavior,
                })
                candidate_results.append(item)

        def quality_rank(candidate: dict[str, Any]) -> tuple[int, int, int]:
            compile_ok = int(bool(candidate["candidate_compilation"].get("passed")))
            rules_ok = int(bool(candidate["static_rule_proxies"].get("rule_adherence_proxy_pass")))
            behavior = candidate["semantic_differential_test"].get("status")
            behavior_ok = int(behavior == "PASS")
            # Highest rank requires all three independent gates to pass.
            return (compile_ok * rules_ok * behavior_ok, compile_ok * behavior_ok, compile_ok)

        selected = max(candidate_results, key=quality_rank)
        selected_source = ROOT / selected["candidate_path"]
        stable_path = output_dir / f"{slug}_generated.c"
        shutil.copyfile(selected_source, stable_path)
        stable_result = {
            **selected,
            "candidate_path": str(stable_path.relative_to(ROOT)),
            "selected_candidate_index": selected["candidate_index"],
        }
        records.append({
            "split": args.split,
            "program_id": program_id,
            "original_path": str(original_path.relative_to(ROOT)) if original_path else None,
            "candidate_path": str(stable_path.relative_to(ROOT)),
            "candidate_nonempty": bool(stable_path.read_text(encoding="utf-8").strip()),
            "selected_candidate_index": selected["candidate_index"],
            "candidate_compilation": stable_result["candidate_compilation"],
            "static_rule_proxies": stable_result["static_rule_proxies"],
            "semantic_differential_test": stable_result["semantic_differential_test"],
            "candidates_generated": len(decoded),
            "all_candidates": candidate_results,
            "original_compilation": original_compile,
        })

    report = {
        "status": "EVALUATION_COMPLETED",
        "split": args.split,
        "num_examples": len(records),
        "device": get_device_summary(),
        "base_model": config["_resolved_model_path"],
        "adapter_path": str(adapter_path.relative_to(ROOT)),
        "purpose": config["experiment"].get("purpose"),
        "generalization_claim_allowed": False,
        "generation_config": gen_cfg,
        "results": records,
        "interpretation": [
            "Each input generates several beam candidates; compiler and differential gates are run per candidate.",
            "The selected candidate is the highest-ranked output by hard-gate results; it may still fail acceptance.",
            "Lexical transformation checks are proxies, not AST proofs.",
            "This five-example dataset supports pipeline debugging only, not generalization claims.",
        ],
    }
    report_dir = ROOT / config["output"]["report_dir"]
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"evaluation_{args.split}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Evaluation finished for split: {args.split}")
    print(f"Examples evaluated: {len(records)}")
    print(f"Candidates per example requested: {num_return}")
    print(f"Candidates directory: {output_dir.relative_to(ROOT)}")
    print(f"Report: {report_path.relative_to(ROOT)}")
    for rec in records:
        print(
            f"[{rec['program_id']}] candidates={rec['candidates_generated']} "
            f"selected={rec['selected_candidate_index']} "
            f"compile={rec['candidate_compilation'].get('passed', False)} "
            f"rules={rec['static_rule_proxies'].get('rule_adherence_proxy_pass', False)} "
            f"behavior={rec['semantic_differential_test'].get('status', 'N/A')}"
        )
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate compact-prompt Generator A with beam candidate selection")
    parser.add_argument("--config", type=Path, default=Path("configs/generator_a_v2.json"))
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument("--max-examples", type=int, default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.max_examples is not None and args.max_examples < 1:
        print("--max-examples must be positive", file=sys.stderr)
        return 2
    try:
        return evaluate(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Evaluate Qwen Generator A or the deterministic fallback on the C dataset.

Run from the repository root:
  python -m src.models.evaluate_qwen_generator_a --split validation --backend fallback
  python -m src.models.evaluate_qwen_generator_a --split validation --backend qwen
  python -m src.models.evaluate_qwen_generator_a --split test --backend qwen

An accepted candidate must compile, satisfy the project's configured lexical
transformation proxies, and pass all available differential tests. Lexical
proxies are not AST proofs and cannot establish absence of undefined behavior.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
ADAPTER_PATH = ROOT / "models/checkpoints/generator_a_qwen_1.5b_rtx/final_adapter"
DATA_ROOT = ROOT / "data/dataset_v1"
DEFAULT_DATA = ROOT / "data/training_v3/generator_a_train_v5.jsonl"
OUTPUT_ROOT = ROOT / "results/qwen_generator_a"
TIMEOUT_SECONDS = 3.0
SYSTEM_PROMPT = (
    "You are an expert C source code obfuscator. Obfuscate the provided C "
    "code while strictly maintaining functional behavior. Return only the "
    "complete transformed C source code, without Markdown fences or commentary."
)

# Reuse the repository's existing proxy definitions and specification semantics.
try:
    from src.models.evaluate_generator_a import static_rule_proxies
    from src.models.hybrid_fallback import apply_ast_fallback_obfuscation
except ImportError as exc:
    raise ImportError(
        "Run this module from the repository root with "
        "'python -m src.models.evaluate_qwen_generator_a'."
    ) from exc


def clean_generated_code(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:c|C)?\s*(.*?)```", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()
    return text + ("\n" if text else "")


def normalize_output(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()).strip()


def load_test_inputs(program_id: str) -> list[dict[str, str]]:
    path = DATA_ROOT / program_id / "tests.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing tests file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("tests", "test_cases", "cases", "inputs", "stdin_cases"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError(f"Unsupported tests.json format: {path}")

    tests: list[dict[str, str]] = []
    for index, case in enumerate(data, start=1):
        if isinstance(case, str):
            tests.append({"name": f"legacy_{index}", "stdin": case})
        elif isinstance(case, dict) and "stdin" in case:
            stdin = case["stdin"]
            if isinstance(stdin, list):
                stdin = " ".join(map(str, stdin))
            tests.append({
                "name": str(case.get("name", f"test_{index}")),
                "stdin": stdin if isinstance(stdin, str) else str(stdin),
            })
        elif isinstance(case, dict):
            found = next((case[key] for key in ("input", "input_data", "stdin_text") if key in case), None)
            if found is not None:
                tests.append({
                    "name": str(case.get("name", f"test_{index}")),
                    "stdin": found if isinstance(found, str) else str(found),
                })
            else:
                raise ValueError(f"Test case {index} in {path} has no stdin/input field.")
        else:
            raise ValueError(f"Unsupported test case {index} in {path}: {type(case).__name__}")
    return tests


def load_records(split: str) -> list[dict[str, Any]]:
    if split == "train":
        if not DEFAULT_DATA.is_file():
            raise FileNotFoundError(f"Training split not found: {DEFAULT_DATA}")
        rows = [
            json.loads(line)
            for line in DEFAULT_DATA.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for row in rows:
            row["original_path"] = DATA_ROOT / str(row["program_id"]) / "original.c"
        return rows

    program_id = "program_04" if split == "validation" else "program_05"
    original_path = DATA_ROOT / program_id / "original.c"
    if not original_path.is_file():
        raise FileNotFoundError(f"Original C source not found: {original_path}")
    source = original_path.read_text(encoding="utf-8")
    prompt = (
        "// Task: Obfuscate C source code while preserving behavior.\n"
        "Return only the transformed C program.\n\n"
        + source
    )
    return [{
        "program_id": program_id,
        "input_text": prompt,
        "original_path": original_path,
    }]


def choose_compiler() -> str:
    compiler = shutil.which("clang") or shutil.which("gcc") or shutil.which("cc")
    if not compiler:
        raise RuntimeError("No C compiler found. Install clang or GCC first.")
    return compiler


def compile_source(source_path: Path, executable_path: Path, compiler: str, flags: list[str]) -> dict[str, Any]:
    cmd = [compiler, *flags, str(source_path), "-o", str(executable_path)]
    try:
        result = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
        )
        return {
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-4000:],
            "command": cmd,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "passed": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "command": cmd,
        }


def run_behavior(original_exe: Path, candidate_exe: Path, tests: list[dict[str, str]]) -> dict[str, Any]:
    if not tests:
        return {"status": "NOT_EVALUATED", "reason": "No test inputs found", "passed_cases": 0, "total_cases": 0, "failures": []}
    passed = 0
    failures: list[dict[str, Any]] = []
    for test in tests:
        runs: list[dict[str, Any]] = []
        for executable in (original_exe, candidate_exe):
            try:
                result = subprocess.run(
                    [str(executable)],
                    cwd=ROOT,
                    input=test["stdin"],
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_SECONDS,
                    check=False,
                )
                runs.append({
                    "timeout": False,
                    "returncode": result.returncode,
                    "stdout": normalize_output(result.stdout),
                    "stderr": result.stderr.strip(),
                })
            except subprocess.TimeoutExpired:
                runs.append({"timeout": True, "returncode": None, "stdout": None, "stderr": "Execution timed out"})
            except OSError as exc:
                runs.append({"timeout": False, "returncode": None, "stdout": None, "stderr": str(exc)})
        original_run, candidate_run = runs
        ok = (
            not original_run["timeout"]
            and not candidate_run["timeout"]
            and original_run["returncode"] == candidate_run["returncode"]
            and original_run["stdout"] == candidate_run["stdout"]
        )
        if ok:
            passed += 1
        else:
            failures.append({
                "test": test["name"],
                "stdin": test["stdin"],
                "original": original_run,
                "candidate": candidate_run,
            })
    return {
        "status": "PASS" if passed == len(tests) else "FAIL",
        "passed_cases": passed,
        "total_cases": len(tests),
        "failures": failures,
        "comparison": "normalized stdout and return code; stderr is recorded but not compared",
    }


def assess_candidate(
    program_id: str,
    candidate_name: str,
    code: str,
    original_path: Path,
    tests: list[dict[str, str]],
    compiler: str,
    compiler_flags: list[str],
    specification: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    candidate_path = output_dir / "candidates" / f"{program_id}_{candidate_name}.c"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(code, encoding="utf-8")
    original_code = original_path.read_text(encoding="utf-8")
    rules = static_rule_proxies(original_code, code, specification)

    original_exe = output_dir / "executables" / f"{program_id}_original"
    candidate_exe = output_dir / "executables" / f"{program_id}_{candidate_name}"
    original_exe.parent.mkdir(parents=True, exist_ok=True)
    original_compile = compile_source(original_path, original_exe, compiler, compiler_flags)
    candidate_compile = compile_source(candidate_path, candidate_exe, compiler, compiler_flags)

    if not original_compile["passed"]:
        behavior = {
            "status": "NOT_EVALUATED",
            "reason": "Original program failed to compile",
            "passed_cases": 0,
            "total_cases": len(tests),
            "failures": [],
        }
    elif not candidate_compile["passed"]:
        behavior = {
            "status": "NOT_EVALUATED",
            "reason": "Candidate failed to compile",
            "passed_cases": 0,
            "total_cases": len(tests),
            "failures": [],
        }
    else:
        behavior = run_behavior(original_exe, candidate_exe, tests)

    accepted = (
        original_compile["passed"]
        and candidate_compile["passed"]
        and bool(rules.get("rule_adherence_proxy_pass"))
        and behavior["status"] == "PASS"
    )
    return {
        "candidate_name": candidate_name,
        "candidate_path": str(candidate_path.relative_to(ROOT)),
        "original_compile": original_compile,
        "candidate_compile": candidate_compile,
        "rule_checks": rules,
        "behavior": behavior,
        "accepted": accepted,
    }


def load_qwen(adapter_path: Path):
    if not adapter_path.is_dir():
        raise FileNotFoundError(
            f"Qwen adapter not found: {adapter_path}\n"
            "Ask your teammate to send the final_adapter directory from "
            "models/checkpoints/generator_a_qwen_1.5b_rtx/final_adapter."
        )
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    model_id = MODEL_ID
    device = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    tokenizer_source = str(adapter_path) if (adapter_path / "tokenizer_config.json").is_file() else model_id
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    kwargs: dict[str, Any] = {"low_cpu_mem_usage": True}
    if device.type == "cuda" and importlib.util.find_spec("bitsandbytes") is not None:
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        kwargs["device_map"] = "auto"
    else:
        kwargs["torch_dtype"] = torch.float16 if device.type in ("cuda", "mps") else torch.float32

    print(f"Loading base model {model_id} on {device}; this may download model weights.")
    base = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    if "device_map" not in kwargs:
        base = base.to(device)
    model = PeftModel.from_pretrained(base, str(adapter_path))
    model.eval()
    return model, tokenizer


def generate_qwen(model: Any, tokenizer: Any, input_text: str) -> str:
    import torch

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": input_text},
    ]
    token_ids = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    )
    if isinstance(token_ids, dict):
        token_ids = token_ids["input_ids"]
    try:
        target_device = model.get_input_embeddings().weight.device
    except Exception:
        target_device = next(model.parameters()).device
    token_ids = token_ids.to(target_device)
    with torch.inference_mode():
        output = model.generate(
            input_ids=token_ids,
            max_new_tokens=768,
            do_sample=False,
            num_beams=1,
            repetition_penalty=1.05,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    return clean_generated_code(
        tokenizer.decode(output[0, token_ids.shape[1]:], skip_special_tokens=True)
    )


def evaluate(args: argparse.Namespace) -> int:
    spec_path = ROOT / "configs/specification_v1.json"
    specification = json.loads(spec_path.read_text(encoding="utf-8"))
    if not specification.get("required_transformations"):
        raise ValueError("Specification has no required transformations.")
    compiler = choose_compiler()
    compiler_flags = list(specification.get("compiler_flags", ["-std=c11"]))
    rows = load_records(args.split)
    if args.max_examples is not None:
        rows = rows[:args.max_examples]
    if not rows:
        raise ValueError(f"No examples found for split {args.split}.")

    adapter_exists = ADAPTER_PATH.is_dir()
    backend = args.backend
    if backend == "auto":
        backend = "qwen" if adapter_exists else "fallback"
    if backend == "qwen" and not adapter_exists:
        raise FileNotFoundError(
            f"Adapter is missing at {ADAPTER_PATH}. Request it from your teammate; "
            "use --backend fallback for local pipeline validation meanwhile."
        )

    model = tokenizer = None
    if backend == "qwen":
        model, tokenizer = load_qwen(ADAPTER_PATH)
    else:
        print(
            "WARNING: FALLBACK-ONLY evaluation. No Qwen model is being evaluated. "
            "Identifier renaming alone cannot meet the full configured transformation specification."
        )

    output_dir = OUTPUT_ROOT / args.split
    (output_dir / "candidates").mkdir(parents=True, exist_ok=True)
    (output_dir / "executables").mkdir(parents=True, exist_ok=True)
    records_report: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        program_id = str(row.get("program_id") or f"{args.split}_{index:02d}")
        original_path = Path(row.get("original_path", DATA_ROOT / program_id / "original.c"))
        if not original_path.is_absolute():
            original_path = ROOT / original_path
        if not original_path.is_file():
            raise FileNotFoundError(f"Original source not found for {program_id}: {original_path}")
        tests = load_test_inputs(program_id)
        attempts: list[dict[str, Any]] = []

        if backend == "qwen":
            neural_code = generate_qwen(model, tokenizer, str(row["input_text"]))
            neural_result = assess_candidate(
                program_id, "qwen", neural_code, original_path, tests, compiler,
                compiler_flags, specification, output_dir,
            )
            attempts.append(neural_result)

        if backend == "fallback" or not any(item["accepted"] for item in attempts):
            fallback_code = apply_ast_fallback_obfuscation(
                original_path.read_text(encoding="utf-8")
            )
            fallback_result = assess_candidate(
                program_id, "fallback", fallback_code, original_path, tests, compiler,
                compiler_flags, specification, output_dir,
            )
            attempts.append(fallback_result)

        accepted = [item for item in attempts if item["accepted"]]
        if accepted:
            selected = accepted[0]
        else:
            selected = max(
                attempts,
                key=lambda item: (
                    item["candidate_compile"]["passed"],
                    item["behavior"]["status"] == "PASS",
                    bool(item["rule_checks"].get("rule_adherence_proxy_pass")),
                ),
            )
        record = {
            "program_id": program_id,
            "selected_candidate": selected["candidate_name"],
            "accepted": selected["accepted"],
            "attempts": attempts,
            "note": (
                "Acceptance uses compilation, lexical transformation proxies, and differential tests. "
                "The lexical proxies are not AST-level proof."
            ),
        }
        records_report.append(record)
        print(
            f"[{program_id}] selected={selected['candidate_name']} "
            f"compile={selected['candidate_compile']['passed']} "
            f"rules={selected['rule_checks'].get('rule_adherence_proxy_pass')} "
            f"behavior={selected['behavior']['status']} accepted={selected['accepted']}"
        )

    report = {
        "model": MODEL_ID if backend == "qwen" else None,
        "backend": backend,
        "split": args.split,
        "dataset": str(DEFAULT_DATA.relative_to(ROOT)) if args.split == "train" else None,
        "compiler": compiler,
        "compiler_flags": compiler_flags,
        "program_count": len(records_report),
        "accepted_count": sum(r["accepted"] for r in records_report),
        "records": records_report,
        "limitations": [
            "Lexical rule proxies are not AST proofs.",
            "Differential tests only cover the inputs in each program's tests.json.",
            "A fallback-only run is not a Qwen-model evaluation.",
        ],
    }
    output_path = output_dir / "evaluation.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nAccepted: {report['accepted_count']}/{report['program_count']}")
    print(f"Report: {output_path.relative_to(ROOT)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Qwen Generator A with actual C tests and rule proxies.")
    parser.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    parser.add_argument("--backend", choices=("auto", "qwen", "fallback"), default="auto")
    parser.add_argument("--max-examples", type=int, default=None)
    args = parser.parse_args()
    evaluate(args)


if __name__ == "__main__":
    main()
